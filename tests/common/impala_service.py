# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
#
# Basic object model of a Impala Services (impalad + statestored). Provides a way to
# programatically interact with the services and perform operations such as querying
# the debug webpage, getting metric values, or creating client connections.

from __future__ import absolute_import, division, print_function
from collections import defaultdict
from datetime import datetime
import json
import logging
import os
import re
import socket
import subprocess
from time import sleep, time

import requests
from thrift.transport.TSocket import TSocket
from thrift.transport.TTransport import TBufferedTransport

from tests.common.impala_connection import create_connection, create_ldap_connection
from tests.common.network import to_host_port, CERT_TO_CA_MAP
from tests.common.test_vector import BEESWAX, HS2, HS2_HTTP

LOG = logging.getLogger('impala_service')
LOG.setLevel(level=logging.DEBUG)

WEBSERVER_USERNAME = os.environ.get('IMPALA_WEBSERVER_USERNAME', None)
WEBSERVER_PASSWORD = os.environ.get('IMPALA_WEBSERVER_PASSWORD', None)


# Base class for all Impala services
# TODO: Refactor the retry/timeout logic into a common place.
class BaseImpalaService(object):
  def __init__(self, hostname, webserver_interface, webserver_port,
      webserver_certificate_file, ssl_client_ca_certificate_file):
    self.hostname = hostname
    self.webserver_interface = webserver_interface
    if webserver_interface == "":
      # If no webserver interface was specified, just use the hostname.
      self.webserver_interface = hostname
    self.webserver_port = webserver_port
    self.webserver_certificate_file = webserver_certificate_file
    self.ssl_client_ca_certificate_file = ssl_client_ca_certificate_file
    self.webserver_username_password = None
    if WEBSERVER_USERNAME is not None and WEBSERVER_PASSWORD is not None:
      self.webserver_username_password = (WEBSERVER_USERNAME, WEBSERVER_PASSWORD)

  def open_debug_webpage(self, page_name, timeout=10, interval=1):
    start_time = time()

    while (time() - start_time < timeout):
      try:
        protocol = "http"
        if self.webserver_certificate_file != "":
          protocol = "https"
        host_port = to_host_port(self.webserver_interface, self.webserver_port)
        url = "%s://%s/%s" % (protocol, host_port, page_name)
        cert = self.webserver_certificate_file
        # Instead of cert use its CA cert if available.
        file_part = cert.split("/")[-1]
        if file_part in CERT_TO_CA_MAP:
          cert = cert.replace(file_part, CERT_TO_CA_MAP[file_part])
        return requests.get(url, verify=cert, auth=self.webserver_username_password)
      except Exception as e:
        LOG.info("Debug webpage not yet available: %s", str(e))
      sleep(interval)
    assert 0, 'Debug webpage did not become available in expected time.'

  def read_debug_webpage(self, page_name, timeout=10, interval=1):
    return self.open_debug_webpage(page_name, timeout=timeout, interval=interval).text

  def get_debug_webpage_json(self, page_name, timeout=10, interval=1):
    """Returns the json for the given Impala debug webpage, eg. '/queries'"""
    return json.loads(self.read_debug_webpage(
        page_name + "?json", timeout=timeout, interval=interval))

  def dump_debug_webpage_json(self, page_name, filename):
    """Dumps the json for a given Impalad debug webpage to the specified file.
       Prints the JSON with indenting to be somewhat human readable."""
    debug_json = self.get_debug_webpage_json(page_name)
    with open(filename, "w") as json_out:
      json.dump(debug_json, json_out, indent=2)

  def get_metric_value(self, metric_name, default_value=None):
    """Returns the value of the the given metric name from the Impala debug webpage"""
    return self.get_metric_values([metric_name], [default_value])[0]

  def get_metric_values(self, metric_names, default_values=None):
    """Returns the value of the given metrics from the Impala debug webpage. If
    default_values is provided and a metric is not present, the default value
    is returned instead."""
    if default_values is None:
      default_values = [None for m in metric_names]
    assert len(metric_names) == len(default_values)
    metrics = self.get_debug_webpage_json('jsonmetrics')
    return [metrics.get(metric_name, default_value)
            for metric_name, default_value in zip(metric_names, default_values)]

  def get_flag_current_value(self, flag):
    """Returns the value of the the given flag name from the Impala /varz debug webpage.
    If the flag does not exist it returns None."""
    varz = self.get_debug_webpage_json("varz")
    for var in varz.get("flags"):
      if var["name"] == flag:
        return var["current"]
    return None

  def get_flag_current_values(self):
    """Returns the value of all flags from the Impala /varz debug webpage."""
    flags = dict()
    varz = self.get_debug_webpage_json("varz")
    for var in varz.get("flags"):
      flags[var['name']] = var['current']
    return flags

  def wait_for_metric_value(self, metric_name, expected_value, timeout=10, interval=1,
      allow_greater=False):
    start_time = time()
    total_wait = 0
    while (total_wait < timeout):
      LOG.info("Getting metric: %s from %s:%s" %
          (metric_name, self.hostname, self.webserver_port))
      value = None
      try:
        value = self.get_metric_value(metric_name)
      except Exception as e:
        LOG.error(e)

      # if allow_greater is True we wait until the metric value becomes >= the expected
      # value.
      if (value == expected_value) or (allow_greater and value >= expected_value):
        LOG.info("Metric '{0}' has reached desired value: {1}. total_wait: {2}s".format(
          metric_name, value, total_wait))
        return value
      else:
        LOG.info("Waiting for metric value '{0}'{1}{2}. Current value: {3}. "
                 "total_wait: {4}s".format(
                   metric_name, ('>=' if allow_greater else '='), expected_value, value,
                   total_wait))
      LOG.info("Sleeping %ds before next retry." % interval)
      sleep(interval)
      total_wait = time() - start_time

    LOG.info("Metric {0} did not reach value {1} in {2}s. Actual value was '{3}'. "
             "total_wait: {4}s. Failing...".format(
               metric_name, expected_value, timeout, value, total_wait))
    self.__metric_timeout_assert(metric_name, expected_value, timeout, value)

  def __request_minidump(self, pid):
    """
    Impala processes (impalad, catalogd, statestored) have a signal handler for
    SIGUSR1 that dumps a minidump. This sends a SIGUSR1 to the specified pid
    to trigger a minidump. Note that this will not work for processes that don't
    implement a handler for SIGUSR1. This does not wait for the minidump to be
    generated, so callers will need to consider this.
    """
    cmd = ["kill", "-SIGUSR1", pid]
    subprocess.check_output(cmd)

  def __metric_timeout_assert(self, metric_name, expected_value, timeout, actual_value):
    """
    Helper function to dump diagnostic information for debugging a metric timeout and
    then assert.
    """
    impala_home = os.environ["IMPALA_HOME"]
    log_dir = os.environ["IMPALA_LOGS_DIR"]

    # Create a diagnostic directory to contain all the relevent information
    datetime_string = datetime.now().strftime("%Y%m%d_%H:%M:%S")
    diag_dir = os.path.join(log_dir, "metric_timeout_diags_{0}".format(datetime_string))
    if not os.path.exists(diag_dir):
      os.makedirs(diag_dir)

    # Read debug pages from the Web UI and dump them to files in the diagnostic
    # directory
    json_dir = os.path.join(diag_dir, "json")
    if not os.path.exists(json_dir):
      os.makedirs(json_dir)
    json_diag_string = "Dumping debug webpages in JSON format...\n"
    debug_pages = ["memz", "metrics", "queries", "sessions", "threadz", "rpcz"]
    for debug_page in debug_pages:
      json_filename = os.path.join(json_dir, "{0}.json".format(debug_page))
      self.dump_debug_webpage_json(debug_page, json_filename)
      json_filename_rewritten = json_filename.replace(impala_home, "$IMPALA_HOME")
      json_diag_string += \
          "Dumped {0} JSON to {1}\n".format(debug_page, json_filename_rewritten)

    # Requests a minidump for each running impalad/catalogd. The minidump will be
    # written to the processes's minidump_path. For simplicity, we leave it there,
    # as it will be preserved along with everything else in the log directory.
    impalad_pids = subprocess.check_output(["pgrep", "impalad"],
        universal_newlines=True).split("\n")[:-1]
    catalogd_pids = subprocess.check_output(["pgrep", "catalogd"],
        universal_newlines=True).split("\n")[:-1]
    minidump_diag_string = "Dumping minidumps for impalads/catalogds...\n"
    for pid in impalad_pids:
      self.__request_minidump(pid)
      minidump_diag_string += "Dumped minidump for Impalad PID {0}\n".format(pid)
    for pid in catalogd_pids:
      self.__request_minidump(pid)
      minidump_diag_string += "Dumped minidump for Catalogd PID {0}\n".format(pid)

    # This is not a critical path, so sleep 30 seconds to be sure that the minidumps
    # have been written.
    sleep(30)

    # Now, fire the assert with the information about the dumps. This provides
    # information about where to find the json files and other diagnostics.
    # This is in the logs directory, so it should be packed up along with everything
    # else for automated jobs.
    assert_string = \
        "Metric {0} did not reach value {1} in {2}s. Actual value was '{3}'.\n" \
        .format(metric_name, expected_value, timeout, actual_value)
    assert_string += json_diag_string
    assert_string += minidump_diag_string
    assert 0, assert_string

  def get_catalog_object_dump(self, object_type, object_name):
    """ Gets the web-page for the given 'object_type' and 'object_name'."""
    return self.read_debug_webpage('catalog_object?object_type=%s&object_name=%s' %
        (object_type, object_name))

  def get_catalog_objects(self, excludes=['_impala_builtins']):
    """ Returns a dictionary containing all catalog objects. Each entry's key is the fully
        qualified object name and the value is a tuple of the form (type, version).
        Does not return databases listed in the 'excludes' list."""
    catalog = self.get_debug_webpage_json('catalog')
    objects = {}
    for db_desc in catalog["databases"]:
      db_name = db_desc["name"]
      if db_name in excludes:
        continue
      db = self.get_catalog_object_dump('DATABASE', db_name)
      objects[db_name] = ('DATABASE', self.extract_catalog_object_version(db))
      for table_desc in db_desc["tables"]:
        table_name = table_desc["fqtn"]
        table = self.get_catalog_object_dump('TABLE', table_name)
        objects[table_name] = ('TABLE', self.extract_catalog_object_version(table))
    return objects

  def extract_catalog_object_version(self, thrift_txt):
    """ Extracts and returns the version of the catalog object's 'thrift_txt'
        representation."""
    result = re.search(r'catalog_version \(i64\) = (\d+)', thrift_txt)
    assert result, 'Unable to find catalog version in object: ' + thrift_txt
    return int(result.group(1))


# Allows for interacting with an Impalad instance to perform operations such as creating
# new connections or accessing the debug webpage.
class ImpaladService(BaseImpalaService):
  def __init__(self, hostname, webserver_interface="", external_interface="",
      webserver_port=25000, beeswax_port=21000, krpc_port=27000, hs2_port=21050,
      hs2_http_port=28000, webserver_certificate_file="",
      ssl_client_ca_certificate_file=""):
    super(ImpaladService, self).__init__(
        hostname, webserver_interface, webserver_port, webserver_certificate_file,
        ssl_client_ca_certificate_file)
    self.external_interface = external_interface if external_interface else hostname
    self.beeswax_port = beeswax_port
    self.krpc_port = krpc_port
    self.hs2_port = hs2_port
    self.hs2_http_port = hs2_http_port

  def get_num_known_live_executors(self, timeout=30, interval=1,
      include_shutting_down=True):
    return self.get_num_known_live_backends(timeout=timeout,
                                            interval=interval,
                                            include_shutting_down=include_shutting_down,
                                            only_executors=True)

  def get_num_known_live_backends(self, timeout=30, interval=1,
      include_shutting_down=True, only_coordinators=False, only_executors=False):
    LOG.debug("Getting num_known_live_backends from %s:%s" %
        (self.hostname, self.webserver_port))
    result = self.get_debug_webpage_json('backends', timeout, interval)
    count = 0
    for backend in result['backends']:
      if backend['is_quiescing'] and not include_shutting_down:
        continue
      if only_coordinators and not backend['is_coordinator']:
        continue
      if only_executors and not backend['is_executor']:
        continue
      count += 1
    return count

  def get_executor_groups(self, timeout=30, interval=1):
    """Returns a mapping from executor group name to a list of all KRPC endpoints of a
    group's executors."""
    LOG.debug("Getting executor groups from %s:%s" %
        (self.hostname, self.webserver_port))
    result = self.get_debug_webpage_json('backends', timeout, interval)
    groups = defaultdict(list)
    for backend in result['backends']:
      groups[backend['executor_groups']].append(backend['krpc_address'])
    return groups

  def get_queries_json(self, timeout=30, interval=1):
    """Return the full JSON from the /queries page."""
    return json.loads(
        self.read_debug_webpage('queries?json', timeout=timeout, interval=interval))

  def get_query_locations(self):
    # Returns a dictionary of the format <host_address, num_of_queries_running_there>
    result = self.get_queries_json()
    if result['query_locations'] is not None:
      return dict([(loc["location"], loc["count"]) for loc in result['query_locations']])
    return None

  def get_in_flight_queries(self, timeout=30, interval=1):
    """Returns the number of in flight queries."""
    return self.get_queries_json(timeout=timeout, interval=interval)['in_flight_queries']

  def get_completed_queries(self, timeout=30, interval=1):
    """Returns the number of completed queries."""
    result = self.get_debug_webpage_json('queries', timeout, interval)
    return result['completed_queries']

  def _get_pool_counter(self, pool_name, counter_name, timeout=30, interval=1):
    """Returns the value of the field 'counter_name' in pool 'pool_name' or 0 if the pool
    doesn't exist."""
    result = self.get_debug_webpage_json('admission', timeout, interval)
    pools = result['resource_pools']
    for pool in pools:
      if pool['pool_name'] == pool_name:
        return pool[counter_name]
    return 0

  def get_num_queued_queries(self, pool_name, timeout=30, interval=1):
    """Returns the number of queued queries in pool 'pool_name' or 0 if the pool doesn't
    exist."""
    return self._get_pool_counter(pool_name, 'agg_num_queued', timeout, interval)

  def get_total_admitted_queries(self, pool_name, timeout=30, interval=1):
    """Returns the total number of queries that have been admitted to pool 'pool_name' or
    0 if the pool doesn't exist."""
    return self._get_pool_counter(pool_name, 'total_admitted', timeout, interval)

  def get_num_running_queries(self, pool_name, timeout=30, interval=1):
    """Returns the number of queries currently running in pool 'pool_name' or 0 if the
    pool doesn't exist."""
    return self._get_pool_counter(pool_name, 'agg_num_running', timeout, interval)

  def get_num_in_flight_queries(self, timeout=30, interval=1):
    LOG.info("Getting num_in_flight_queries from %s:%s" %
        (self.hostname, self.webserver_port))
    result = self.read_debug_webpage('inflight_query_ids?raw', timeout, interval)
    return None if result is None else len(
        [line for line in result.split('\n') if line])

  def wait_for_num_in_flight_queries(self, expected_val, timeout=10):
    """Waits for the number of in-flight queries to reach a certain value"""
    start_time = time()
    while (time() - start_time < timeout):
      num_in_flight_queries = self.get_num_in_flight_queries()
      if num_in_flight_queries == expected_val: return True
      sleep(1)
    LOG.info("The number of in flight queries: %s, expected: %s" %
        (num_in_flight_queries, expected_val))
    return False

  def wait_for_num_known_live_backends(self, expected_value, timeout=30, interval=1,
      include_shutting_down=True, early_abort_fn=lambda: False):
    """Poll the debug web server until the number of backends known by this service
    reaches 'expected_value'. 'early_abort_fn' is called periodically and can
    throw an exception if polling should be aborted early."""
    start_time = time()
    while (time() - start_time < timeout):
      early_abort_fn()
      value = None
      try:
        value = self.get_num_known_live_backends(timeout=1, interval=interval,
            include_shutting_down=include_shutting_down)
      except Exception as e:
        LOG.error(e)
      if value == expected_value:
        LOG.info("num_known_live_backends has reached value: %s" % value)
        return value
      else:
        LOG.info("Waiting for num_known_live_backends=%s. Current value: %s" %
            (expected_value, value))
      sleep(interval)
    assert 0, 'num_known_live_backends did not reach expected value in time'

  def read_query_profile_page(self, query_id, timeout=10, interval=1):
    """Fetches the raw contents of the query's runtime profile webpage.
    Fails an assertion if Impala's webserver is unavailable or the query's
    profile page doesn't exist."""
    return self.read_debug_webpage(
        "query_profile?query_id=%s&raw" % (query_id), timeout=timeout, interval=interval)

  def get_query_status(self, query_id, timeout=10, interval=1):
    """Gets the 'Query Status' section of the query's runtime profile."""
    page = self.read_query_profile_page(query_id, timeout=timeout, interval=interval)
    status_line =\
        next((x for x in page.split('\n') if re.search('Query Status:', x)), None)
    return status_line.split('Query Status:')[1].strip()

  def wait_for_query_state(self, client, query_handle, target_state,
                              timeout=10, interval=1):
    """Keeps polling for the query's state using client in the given interval until
    the query's state reaches the target state or the given timeout has been reached."""
    start_time = time()
    while (time() - start_time < timeout):
      try:
        query_state = client.get_state(query_handle)
      except Exception as e:
        LOG.error("Exception while getting state of query {0}\n{1}".format(
            client.handle_id(query_handle), str(e)))
      if query_state == target_state:
        return
      sleep(interval)
    assert target_state == query_state, \
        'Query {0} did not reach query state in time target={1} actual={2}'.format(
            client.handle_id(query_handle), target_state, query_state)
    return

  def wait_for_query_status(self, query_id, expected_content, timeout=30, interval=1):
    """Polls for the query's status in the query profile web page to contain the
    specified content. Returns False if the timeout was reached before a successful
    match, True otherwise."""
    start_time = time()
    query_status = ""
    while (time() - start_time < timeout):
      try:
        query_status = self.get_query_status(
            query_id, timeout=timeout, interval=interval)
        if query_status is None:
          raise Exception("Could not find 'Query Status' section in profile of "
                          "query with id {}".format(query_id))
      except Exception:
        pass
      if expected_content in query_status:
        return True
      sleep(interval)
    return False

  def use_ssl_for_clients(self):
    return self.ssl_client_ca_certificate_file != ""

  def is_port_open(self, host, port):
    try:
      sock = socket.create_connection((host, port), timeout=1)
      sock.close()
      return True
    except Exception:
      return False

  def webserver_port_is_open(self):
    return self.is_port_open(self.webserver_interface, self.webserver_port)

  def create_beeswax_client(self, use_kerberos=False):
    """Creates a new beeswax client connection to the impalad.
    DEPRECATED: Use create_hs2_client() instead."""
    client = create_connection(to_host_port(self.external_interface, self.beeswax_port),
                               use_kerberos, BEESWAX, use_ssl=self.use_ssl_for_clients())
    client.connect()
    return client

  def beeswax_port_is_open(self):
    """Test if the beeswax port is open. Does not need to authenticate."""
    # Check if the port is open first to avoid chatty logging of Thrift connection.
    if not self.is_port_open(self.external_interface, self.beeswax_port): return False

    try:
      # The beeswax client will connect successfully even if not authenticated.
      client = self.create_beeswax_client()
      client.close()
      return True
    except Exception as e:
      return False

  def create_ldap_beeswax_client(self, user, password, use_ssl=False):
    client = create_ldap_connection(to_host_port(self.hostname, self.beeswax_port),
                                    user=user, password=password, use_ssl=use_ssl)
    client.connect()
    return client

  def create_hs2_client(self, user=None):
    """Creates a new HS2 client connection to the impalad"""
    client = create_connection('%s:%d' % (self.external_interface, self.hs2_port),
                               protocol=HS2, user=user,
                               use_ssl=self.use_ssl_for_clients())
    client.connect()
    return client

  def hs2_port_is_open(self):
    """Test if the HS2 port is open. Does not need to authenticate."""
    # Check if the port is open first to avoid chatty logging of Thrift connection.
    if not self.is_port_open(self.external_interface, self.hs2_port): return False

    # Impyla will try to authenticate as part of connecting, so preserve previous logic
    # that uses the HS2 thrift code directly.
    try:
      sock = TSocket(self.external_interface, self.hs2_port)
      transport = TBufferedTransport(sock)
      transport.open()
      transport.close()
      return True
    except Exception as e:
      LOG.info(e)
      return False

  def hs2_http_port_is_open(self):
    # Only check if the port is open, do not create Thrift transport.
    return self.is_port_open(self.external_interface, self.hs2_http_port)

  def create_client(self, protocol):
    """Creates a new client connection for given protocol to this impalad"""
    port = self.hs2_port
    if protocol == HS2_HTTP:
      port = self.hs2_http_port
    if protocol == BEESWAX:
      LOG.warning('beeswax protocol is deprecated.')
      port = self.beeswax_port
    client = create_connection(to_host_port(self.external_interface, port),
                               protocol=protocol)
    client.connect()
    return client

  def create_client_from_vector(self, vector):
    """A shorthand for create_client with test vector as input.
    Vector must have 'protocol' and 'exec_option' dimension.
    Return a client of specified 'protocol' and with cofiguration 'exec_option' set."""
    client = self.create_client(protocol=vector.get_value('protocol'))
    client.set_configuration(vector.get_exec_option_dict())
    return client


# Allows for interacting with the StateStore service to perform operations such as
# accessing the debug webpage.
class StateStoredService(BaseImpalaService):
  def __init__(self, hostname, webserver_interface, webserver_port,
      webserver_certificate_file, ssl_client_ca_certificate_file, service_port):
    super(StateStoredService, self).__init__(
        hostname, webserver_interface, webserver_port, webserver_certificate_file,
        ssl_client_ca_certificate_file)
    self.service_port = service_port

  def wait_for_live_subscribers(self, num_subscribers, timeout=15, interval=1):
    self.wait_for_metric_value('statestore.live-backends', num_subscribers,
                               timeout=timeout, interval=interval)

  def get_statestore_service_port(self):
    return self.service_port


# Allows for interacting with the Catalog service to perform operations such as
# accessing the debug webpage.
class CatalogdService(BaseImpalaService):
  def __init__(self, hostname, webserver_interface, webserver_port,
      webserver_certificate_file, ssl_client_ca_certificate_file, service_port):
    super(CatalogdService, self).__init__(
        hostname, webserver_interface, webserver_port, webserver_certificate_file,
        ssl_client_ca_certificate_file)
    self.service_port = service_port

  def get_catalog_version(self, timeout=10, interval=1):
    """ Gets catalogd's latest catalog version. Retry for 'timeout'
        seconds, sleeping 'interval' seconds between tries. If the
        version cannot be obtained, this method fails."""
    start_time = time()
    while (time() - start_time < timeout):
      try:
        info = self.get_debug_webpage_json('catalog')
        if "version" in info: return info['version']
      except Exception:
        LOG.info('Catalogd version not yet available.')
      sleep(interval)
    assert False, 'Catalog version not ready in expected time.'

  def get_catalog_service_port(self):
    return self.service_port

  def verify_table_metadata_loaded(self, db, table, expect_loaded=True, timeout_s=10):
    page_url = "table_metrics?json&name=%s.%s" % (db, table)
    start_time = time()
    while (time() - start_time < timeout_s):
      response = self.open_debug_webpage(page_url)
      assert response.status_code == requests.codes.ok
      response_json = json.loads(response.text)
      assert "table_metrics" in response_json
      table_metrics = response_json["table_metrics"]
      if expect_loaded:
        if "Table not yet loaded" not in table_metrics:
          return
        LOG.info("Table {0}.{1} is not loaded".format(db, table))
      else:
        if "Table not yet loaded" in table_metrics:
          return
        LOG.info("Table {0}.{1} is loaded".format(db, table))
      sleep(1)
    assert False, "Timeout waiting table {0}.{1} to be {2}".format(
        db, table, "loaded" if expect_loaded else "not loaded")

class AdmissiondService(BaseImpalaService):
  def __init__(self, hostname, webserver_interface, webserver_port,
      webserver_certificate_file, ssl_client_ca_certificate_file):
    super(AdmissiondService, self).__init__(
        hostname, webserver_interface, webserver_port, webserver_certificate_file,
        ssl_client_ca_certificate_file)
