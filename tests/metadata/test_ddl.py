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

from __future__ import absolute_import, division, print_function
from builtins import map, range
import getpass
import itertools
import pytest
import re
import time
import threading
from multiprocessing.pool import ThreadPool
from multiprocessing import TimeoutError

from copy import deepcopy
from tests.metadata.test_ddl_base import TestDdlBase
from tests.common.environ import (HIVE_MAJOR_VERSION)
from tests.common.file_utils import create_table_from_orc
from tests.common.impala_connection import (
    FINISHED, INITIALIZED, IMPALA_CONNECTION_EXCEPTION, PENDING, RUNNING)
from tests.common.impala_test_suite import LOG
from tests.common.parametrize import UniqueDatabase
from tests.common.skip import (
    SkipIfDockerizedCluster,
    SkipIfFS,
    SkipIfHive2,
    SkipIfKudu,
    SkipIfLocal)
from tests.common.test_dimensions import create_single_exec_option_dimension
from tests.common.test_dimensions import (create_exec_option_dimension,
    create_client_protocol_dimension, create_exec_option_dimension_from_dict)
from tests.common.test_vector import ImpalaTestDimension
from tests.util.filesystem_utils import (
    get_fs_path,
    WAREHOUSE,
    WAREHOUSE_PREFIX,
    IS_HDFS,
    IS_S3,
    IS_ADLS,
    IS_OZONE,
    FILESYSTEM_NAME)
from tests.common.impala_cluster import ImpalaCluster
from tests.util.filesystem_utils import FILESYSTEM_PREFIX
from tests.util.parse_util import parse_duration_string_ms
from tests.util.shell_util import dump_server_stacktraces


def get_trash_path(bucket, path):
  if IS_OZONE:
    return get_fs_path('/{0}/.Trash/{1}/Current{2}/{0}/{3}'.format(bucket,
        getpass.getuser(), WAREHOUSE_PREFIX, path))
  return '/user/{0}/.Trash/Current/{1}/{2}'.format(getpass.getuser(), bucket, path)


# Validates DDL statements (create, drop)
class TestDdlStatements(TestDdlBase):
  @SkipIfLocal.hdfs_client
  def test_drop_table_with_purge(self, unique_database):
    """This test checks if the table data is permanently deleted in
    DROP TABLE <tbl> PURGE queries"""
    self.client.execute("create table {0}.t1(i int)".format(unique_database))
    self.client.execute("create table {0}.t2(i int)".format(unique_database))
    # Create sample test data files under the table directories
    dbpath = "{0}/{1}.db".format(WAREHOUSE, unique_database)
    self.filesystem_client.create_file("{}/t1/t1.txt".format(dbpath), file_data='t1')
    self.filesystem_client.create_file("{}/t2/t2.txt".format(dbpath), file_data='t2')
    # Drop the table (without purge) and make sure it exists in trash
    self.client.execute("drop table {0}.t1".format(unique_database))
    assert not self.filesystem_client.exists("{}/t1/t1.txt".format(dbpath))
    assert not self.filesystem_client.exists("{}/t1/".format(dbpath))
    trash = get_trash_path("test-warehouse", unique_database + ".db")
    assert self.filesystem_client.exists("{}/t1/t1.txt".format(trash))
    assert self.filesystem_client.exists("{}/t1".format(trash))
    # Drop the table (with purge) and make sure it doesn't exist in trash
    self.client.execute("drop table {0}.t2 purge".format(unique_database))
    if not IS_S3 and not IS_ADLS:
      # In S3, deletes are eventual. So even though we dropped the table, the files
      # belonging to this table may still be visible for some unbounded time. This
      # happens only with PURGE. A regular DROP TABLE is just a copy of files which is
      # consistent.
      # The ADLS Python client is not strongly consistent, so these files may still be
      # visible after a DROP. (Remove after IMPALA-5335 is resolved)
      assert not self.filesystem_client.exists("{}/t2/".format(dbpath))
      assert not self.filesystem_client.exists("{}/t2/t2.txt".format(dbpath))
    assert not self.filesystem_client.exists("{}/t2/t2.txt".format(trash))
    assert not self.filesystem_client.exists("{}/t2".format(trash))
    # Create an external table t3 and run the same test as above. Make
    # sure the data is not deleted
    self.filesystem_client.make_dir("{}/data_t3/".format(dbpath), permission=777)
    self.filesystem_client.create_file(
        "{}/data_t3/data.txt".format(dbpath), file_data='100')
    self.client.execute("create external table {0}.t3(i int) stored as "
        "textfile location \'{1}/data_t3\'".format(unique_database, dbpath))
    self.client.execute("drop table {0}.t3 purge".format(unique_database))
    assert self.filesystem_client.exists("{}/data_t3/data.txt".format(dbpath))
    self.filesystem_client.delete_file_dir("{}/data_t3".format(dbpath), recursive=True)

  @SkipIfFS.eventually_consistent
  @SkipIfLocal.hdfs_client
  def test_drop_cleans_hdfs_dirs(self, unique_database):
    self.client.execute('use default')
    # Verify the db directory exists
    assert self.filesystem_client.exists(
        "{1}/{0}.db/".format(unique_database, WAREHOUSE))

    self.client.execute("create table {0}.t1(i int)".format(unique_database))
    # Verify the table directory exists
    assert self.filesystem_client.exists(
        "{1}/{0}.db/t1/".format(unique_database, WAREHOUSE))

    # Dropping the table removes the table's directory and preserves the db's directory
    self.client.execute("drop table {0}.t1".format(unique_database))
    assert not self.filesystem_client.exists(
        "{1}/{0}.db/t1/".format(unique_database, WAREHOUSE))
    assert self.filesystem_client.exists(
        "{1}/{0}.db/".format(unique_database, WAREHOUSE))

    # Dropping the db removes the db's directory
    self.client.execute("drop database {0}".format(unique_database))
    assert not self.filesystem_client.exists(
        "{1}/{0}.db/".format(unique_database, WAREHOUSE))

    # Dropping the db using "cascade" removes all tables' and db's directories
    # but keeps the external tables' directory
    self._create_db(unique_database)
    self.client.execute("create table {0}.t1(i int)".format(unique_database))
    self.client.execute("create table {0}.t2(i int)".format(unique_database))
    self.client.execute("create external table {0}.t3(i int) "
        "location '{1}/{0}/t3/'".format(unique_database, WAREHOUSE))
    self.client.execute("drop database {0} cascade".format(unique_database))
    assert not self.filesystem_client.exists(
        "{1}/{0}.db/".format(unique_database, WAREHOUSE))
    assert not self.filesystem_client.exists(
        "{1}/{0}.db/t1/".format(unique_database, WAREHOUSE))
    assert not self.filesystem_client.exists(
        "{1}/{0}.db/t2/".format(unique_database, WAREHOUSE))
    assert self.filesystem_client.exists(
        "{1}/{0}/t3/".format(unique_database, WAREHOUSE))
    self.filesystem_client.delete_file_dir(
        "{1}/{0}/t3/".format(unique_database, WAREHOUSE), recursive=True)
    assert not self.filesystem_client.exists(
        "{1}/{0}/t3/".format(unique_database, WAREHOUSE))
    # Re-create database to make unique_database teardown succeed.
    self._create_db(unique_database)

  @SkipIfFS.eventually_consistent
  @SkipIfLocal.hdfs_client
  def test_truncate_cleans_hdfs_files(self, unique_database):
    # Verify the db directory exists
    assert self.filesystem_client.exists(
        "{1}/{0}.db/".format(unique_database, WAREHOUSE))

    self.client.execute("create table {0}.t1(i int)".format(unique_database))
    # Verify the table directory exists
    assert self.filesystem_client.exists(
        "{1}/{0}.db/t1/".format(unique_database, WAREHOUSE))

    try:
      # If we're testing S3, we want the staging directory to be created.
      self.client.execute("set s3_skip_insert_staging=false")
      # Should have created one file in the table's dir
      self.client.execute("insert into {0}.t1 values (1)".format(unique_database))
      assert len(self.filesystem_client.ls(
          "{1}/{0}.db/t1/".format(unique_database, WAREHOUSE))) == 2

      # Truncating the table removes the data files and the staging directory
      self.client.execute("truncate table {0}.t1".format(unique_database))
      assert len(self.filesystem_client.ls(
          "{1}/{0}.db/t1/".format(unique_database, WAREHOUSE))) == 0

      self.client.execute(
          "create table {0}.t2(i int) partitioned by (p int)".format(unique_database))
      # Verify the table directory exists
      assert self.filesystem_client.exists(
          "{1}/{0}.db/t2/".format(unique_database, WAREHOUSE))

      # Should have created the partition dir, which should contain exactly one file
      self.client.execute(
          "insert into {0}.t2 partition(p=1) values (1)".format(unique_database))
      assert len(self.filesystem_client.ls(
          "{1}/{0}.db/t2/p=1".format(unique_database, WAREHOUSE))) == 1

      # Truncating the table removes the data files and preserves the partition's
      # directory
      self.client.execute("truncate table {0}.t2".format(unique_database))
      assert self.filesystem_client.exists(
          "{1}/{0}.db/t2/p=1".format(unique_database, WAREHOUSE))
      assert len(self.filesystem_client.ls(
          "{1}/{0}.db/t2/p=1".format(unique_database, WAREHOUSE))) == 0
    finally:
      # Reset to its default value.
      self.client.execute("set s3_skip_insert_staging=true")

  @SkipIfFS.incorrent_reported_ec
  @UniqueDatabase.parametrize(sync_ddl=True)
  def test_truncate_table(self, vector, unique_database):
    vector.get_value('exec_option')['abort_on_error'] = False
    self.run_test_case('QueryTest/truncate-table', vector, use_db=unique_database,
        multiple_impalad=self._use_multiple_impalad(vector))

  @UniqueDatabase.parametrize(sync_ddl=True)
  def test_create_database(self, vector, unique_database):
    # The unique_database provides the .test a unique database name which allows
    # us to run this test in parallel with others.
    self.run_test_case('QueryTest/create-database', vector, use_db=unique_database,
        multiple_impalad=self._use_multiple_impalad(vector))

  def test_comment_on_database(self, unique_database):
    comment = self._get_db_comment(unique_database)
    assert '' == comment

    self.client.execute("comment on database {0} is 'comment'".format(unique_database))
    comment = self._get_db_comment(unique_database)
    assert 'comment' == comment

    self.client.execute("comment on database {0} is ''".format(unique_database))
    comment = self._get_db_comment(unique_database)
    assert '' == comment

    self.client.execute("comment on database {0} is '\\'comment\\''".format(
      unique_database))
    comment = self._get_db_comment(unique_database)
    assert "\\'comment\\'" == comment

    self.client.execute("comment on database {0} is null".format(unique_database))
    comment = self._get_db_comment(unique_database)
    assert '' == comment

  def test_alter_database_set_owner(self, unique_database):
    self.client.execute("alter database {0} set owner user foo_user".format(
      unique_database))
    properties = self._get_db_owner_properties(unique_database)
    assert len(properties) == 1
    assert {'foo_user': 'USER'} == properties

    self.client.execute("alter database {0} set owner role foo_role".format(
      unique_database))
    properties = self._get_db_owner_properties(unique_database)
    assert len(properties) == 1
    assert {'foo_role': 'ROLE'} == properties

  def test_metadata_after_alter_database(self, unique_database):
    self.client.execute("create table {0}.tbl (i int)".format(unique_database))
    self.client.execute("create function {0}.f() returns int "
                        "location '{1}/libTestUdfs.so' symbol='NoArgs'"
                        .format(unique_database, WAREHOUSE))
    self.client.execute("alter database {0} set owner user foo_user".format(
      unique_database))
    table_names = self.client.execute("show tables in {0}".format(
      unique_database)).get_data()
    assert "tbl" == table_names
    func_names = self.client.execute("show functions in {0}".format(
      unique_database)).get_data()
    assert "INT\tf()\tNATIVE\ttrue" == func_names

  def test_alter_table_set_owner(self, unique_database):
    table_name = "{0}.test_owner_tbl".format(unique_database)
    self.client.execute("create table {0}(i int)".format(table_name))
    self.client.execute("alter table {0} set owner user foo_user".format(table_name))
    owner = self._get_table_or_view_owner(table_name)
    assert ('foo_user', 'USER') == owner

    self.client.execute("alter table {0} set owner role foo_role".format(table_name))
    owner = self._get_table_or_view_owner(table_name)
    assert ('foo_role', 'ROLE') == owner

  def test_alter_view_set_owner(self, unique_database):
    view_name = "{0}.test_owner_tbl".format(unique_database)
    self.client.execute("create view {0} as select 1".format(view_name))
    self.client.execute("alter view {0} set owner user foo_user".format(view_name))
    owner = self._get_table_or_view_owner(view_name)
    assert ('foo_user', 'USER') == owner

    self.client.execute("alter view {0} set owner role foo_role".format(view_name))
    owner = self._get_table_or_view_owner(view_name)
    assert ('foo_role', 'ROLE') == owner

  # There is a query in QueryTest/create-table that references nested types, which is not
  # supported if old joins and aggs are enabled. Since we do not get any meaningful
  # additional coverage by running a DDL test under the old aggs and joins, it can be
  # skipped.
  @UniqueDatabase.parametrize(sync_ddl=True)
  def test_create_table(self, vector, unique_database):
    vector.get_value('exec_option')['abort_on_error'] = False
    self.run_test_case('QueryTest/create-table', vector, use_db=unique_database,
        multiple_impalad=self._use_multiple_impalad(vector))

  @SkipIfFS.incorrent_reported_ec
  @UniqueDatabase.parametrize(sync_ddl=True)
  def test_create_table_like_table(self, vector, unique_database):
    vector.get_value('exec_option')['abort_on_error'] = False
    self.run_test_case('QueryTest/create-table-like-table', vector,
        use_db=unique_database, multiple_impalad=self._use_multiple_impalad(vector))

  @UniqueDatabase.parametrize(sync_ddl=True)
  def test_create_table_like_file(self, vector, unique_database):
    vector.get_value('exec_option')['abort_on_error'] = False
    self.run_test_case('QueryTest/create-table-like-file', vector,
        use_db=unique_database, multiple_impalad=self._use_multiple_impalad(vector))

  @SkipIfHive2.orc
  @SkipIfFS.hive
  @UniqueDatabase.parametrize(sync_ddl=True)
  def test_create_table_like_file_orc(self, vector, unique_database):
    COMPLEXTYPETBL_PATH = 'test-warehouse/managed/functional_orc_def.db/' \
                          'complextypestbl_orc_def/'
    base_dir = list(filter(lambda s: s.startswith('base'),
      self.filesystem_client.ls(COMPLEXTYPETBL_PATH)))[0]
    bucket_file = list(filter(lambda s: s.startswith('bucket'),
      self.filesystem_client.ls(COMPLEXTYPETBL_PATH + base_dir)))[0]
    vector.get_value('exec_option')['abort_on_error'] = False
    create_table_from_orc(self.client, unique_database,
        'timestamp_with_local_timezone')
    self.run_test_case('QueryTest/create-table-like-file-orc', vector,
        use_db=unique_database, multiple_impalad=self._use_multiple_impalad(vector),
        test_file_vars={
          '$TRANSACTIONAL_COMPLEXTYPESTBL_FILE':
          FILESYSTEM_PREFIX + '/' + COMPLEXTYPETBL_PATH + base_dir + '/' + bucket_file})

  @UniqueDatabase.parametrize(sync_ddl=True)
  def test_create_table_as_select(self, vector, unique_database):
    vector.get_value('exec_option')['abort_on_error'] = False
    self.run_test_case('QueryTest/create-table-as-select', vector,
        use_db=unique_database, multiple_impalad=self._use_multiple_impalad(vector))

  @UniqueDatabase.parametrize(sync_ddl=True)
  @SkipIfKudu.no_hybrid_clock()
  def test_create_kudu(self, vector, unique_database):
    vector.get_value('exec_option')['abort_on_error'] = False
    vector.get_value('exec_option')['kudu_read_mode'] = "READ_AT_SNAPSHOT"
    self.run_test_case('QueryTest/kudu_create', vector, use_db=unique_database,
        multiple_impalad=self._use_multiple_impalad(vector))

  def test_comment_on_table(self, unique_database):
    table = '{0}.comment_table'.format(unique_database)
    self.client.execute("create table {0} (i int)".format(table))

    comment = self._get_table_or_view_comment(table)
    assert comment is None

    self.client.execute("comment on table {0} is 'comment'".format(table))
    comment = self._get_table_or_view_comment(table)
    assert "comment" == comment

    self.client.execute("comment on table {0} is ''".format(table))
    comment = self._get_table_or_view_comment(table)
    assert "" == comment

    self.client.execute("comment on table {0} is '\\'comment\\''".format(table))
    comment = self._get_table_or_view_comment(table)
    assert "\\\\'comment\\\\'" == comment

    self.client.execute("comment on table {0} is null".format(table))
    comment = self._get_table_or_view_comment(table)
    assert comment is None

  def test_comment_on_view(self, unique_database):
    view = '{0}.comment_view'.format(unique_database)
    self.client.execute("create view {0} as select 1".format(view))

    comment = self._get_table_or_view_comment(view)
    assert comment is None

    self.client.execute("comment on view {0} is 'comment'".format(view))
    comment = self._get_table_or_view_comment(view)
    assert "comment" == comment

    self.client.execute("comment on view {0} is ''".format(view))
    comment = self._get_table_or_view_comment(view)
    assert "" == comment

    self.client.execute("comment on view {0} is '\\'comment\\''".format(view))
    comment = self._get_table_or_view_comment(view)
    assert "\\\\'comment\\\\'" == comment

    self.client.execute("comment on view {0} is null".format(view))
    comment = self._get_table_or_view_comment(view)
    assert comment is None

  def test_comment_on_column(self, unique_database):
    table = "{0}.comment_table".format(unique_database)
    self.client.execute("create table {0} (i int) partitioned by (j int)".format(table))

    comment = self._get_column_comment(table, 'i')
    assert '' == comment

    # Updating comment on a regular column.
    self.client.execute("comment on column {0}.i is 'comment 1'".format(table))
    comment = self._get_column_comment(table, 'i')
    assert "comment 1" == comment

    # Updating comment on a partition column.
    self.client.execute("comment on column {0}.j is 'comment 2'".format(table))
    comment = self._get_column_comment(table, 'j')
    assert "comment 2" == comment

    self.client.execute("comment on column {0}.i is ''".format(table))
    comment = self._get_column_comment(table, 'i')
    assert "" == comment

    self.client.execute("comment on column {0}.i is '\\'comment\\''".format(table))
    comment = self._get_column_comment(table, 'i')
    assert "\\'comment\\'" == comment

    self.client.execute("comment on column {0}.i is null".format(table))
    comment = self._get_column_comment(table, 'i')
    assert "" == comment

    view = "{0}.comment_view".format(unique_database)
    self.client.execute("create view {0}(i) as select 1".format(view))

    comment = self._get_column_comment(view, 'i')
    assert "" == comment

    self.client.execute("comment on column {0}.i is 'comment'".format(view))
    comment = self._get_column_comment(view, 'i')
    assert "comment" == comment

    self.client.execute("comment on column {0}.i is ''".format(view))
    comment = self._get_column_comment(view, 'i')
    assert "" == comment

    self.client.execute("comment on column {0}.i is '\\'comment\\''".format(view))
    comment = self._get_column_comment(view, 'i')
    assert "\\'comment\\'" == comment

    self.client.execute("comment on column {0}.i is null".format(view))
    comment = self._get_column_comment(view, 'i')
    assert "" == comment

  @UniqueDatabase.parametrize(sync_ddl=True)
  def test_sync_ddl_drop(self, unique_database):
    """Verifies the catalog gets updated properly when dropping objects with sync_ddl
    enabled"""
    self.client.set_configuration({'sync_ddl': 1})
    # Drop the database immediately after creation (within a statestore heartbeat) and
    # verify the catalog gets updated properly.
    self.client.execute("drop database {0}".format(unique_database))
    assert unique_database not in self.all_db_names()
    # Re-create database to make unique_database teardown succeed.
    self._create_db(unique_database)

  # TODO: don't use hdfs_client
  @SkipIfLocal.hdfs_client
  @SkipIfFS.incorrent_reported_ec
  @UniqueDatabase.parametrize(sync_ddl=True, num_dbs=2)
  def test_alter_table(self, vector, unique_database):
    vector.get_value('exec_option')['abort_on_error'] = False

    # Create an unpartitioned table to get a filesystem directory that does not
    # use the (key=value) format. The directory is automatically cleanup up
    # by the unique_database fixture.
    self.client.execute("create table {0}.part_data (i int)".format(unique_database))
    dbpath = "{1}/{0}.db".format(unique_database, WAREHOUSE)
    assert self.filesystem_client.exists("{}/part_data".format(dbpath))
    self.filesystem_client.create_file(
        "{}/part_data/data.txt".format(dbpath), file_data='1984')
    self.run_test_case('QueryTest/alter-table', vector, use_db=unique_database,
        multiple_impalad=self._use_multiple_impalad(vector))

  @SkipIfFS.hdfs_caching
  @SkipIfLocal.hdfs_client
  @UniqueDatabase.parametrize(sync_ddl=True, num_dbs=2)
  def test_alter_table_hdfs_caching(self, vector, unique_database):
    self.run_test_case('QueryTest/alter-table-hdfs-caching', vector,
        use_db=unique_database, multiple_impalad=self._use_multiple_impalad(vector))

  @UniqueDatabase.parametrize(sync_ddl=True)
  def test_alter_set_column_stats(self, vector, unique_database):
    self.run_test_case('QueryTest/alter-table-set-column-stats', vector,
        use_db=unique_database, multiple_impalad=self._use_multiple_impalad(vector))

  # Run serially as alter waits for catalog to catch up before marking "DDL finished" so
  # we don't have a good way to confirm the alter timeline if catalog gets delayed.
  @pytest.mark.execute_serially
  def test_alter_table_rename_independent(self, vector, unique_database):
    """Tests that two alter table renames run concurrently do not block each other."""

    def table_name(i):
      return "{}.tbl_{}".format(unique_database, i)

    def alter(i, j):
      return "alter table {} rename to {}".format(table_name(i), table_name(j))

    def get_read_lock_duration_ms(profile):
      read_lock_durations = re.findall(r"Got catalog version read lock: [^ ]*", profile)
      assert len(read_lock_durations) == 1
      return parse_duration_string_ms(read_lock_durations[0].split(" ")[-1])

    self.client.execute("create table {} (i int)".format(table_name(1)))
    self.client.execute("create table {} (i int)".format(table_name(2)))
    # Ensure loading metadata is not a factor in alter execution time.
    self.client.execute("describe {}".format(table_name(1)))
    self.client.execute("describe {}".format(table_name(2)))

    new_vector = deepcopy(vector)
    new_vector.get_value('exec_option')['debug_action'] = \
        "catalogd_table_rename_delay:SLEEP@5000"
    with self.create_impala_client_from_vector(new_vector) as client1, \
         self.create_impala_client_from_vector(new_vector) as client2:
      start = time.time()
      handle1 = client1.execute_async(alter(1, 3))
      handle2 = client2.execute_async(alter(2, 4))
      assert client1.wait_for_finished_timeout(handle1, timeout=15)
      assert client2.wait_for_finished_timeout(handle2, timeout=15)
      assert time.time() - start < 15

      profile1 = client1.get_runtime_profile(handle1)
      assert get_read_lock_duration_ms(profile1) < 5000
      profile2 = client2.get_runtime_profile(handle2)
      assert get_read_lock_duration_ms(profile2) < 5000

      client1.close_query(handle1)
      client2.close_query(handle2)

  @UniqueDatabase.parametrize(num_dbs=2)
  def test_concurrent_alter_table_rename(self, vector, unique_database):
    test_self = self

    class ThreadLocalClient(threading.local):
      def __init__(self):
        self.client = test_self.create_impala_client_from_vector(vector)

    pool = ThreadPool(processes=8)
    tlc = ThreadLocalClient()

    def run_rename(i):
      if i % 2 == 0:
        tlc.client.execute("set sync_ddl=1")
      is_partitioned = i % 4 < 2
      tbl_name = "{}.tbl_{}".format(unique_database, i)
      tlc.client.execute("create table {}(i int){}".format(
          tbl_name, "partitioned by(p int)" if is_partitioned else ""))
      if i % 8 < 4:
        # Rename inside the same db
        new_tbl_name = tbl_name + "_new"
      else:
        # Move to another db
        new_tbl_name = "{}2.tbl_{}".format(unique_database, i)
      stmts = [
        "alter table {} rename to {}".format(tbl_name, new_tbl_name),
        "alter table {} rename to {}".format(new_tbl_name, tbl_name),
      ]
      # Move the table back and forth in several rounds
      for _ in range(4):
        for query in stmts:
          # Run the query asynchronously to avoid getting stuck by it
          handle = tlc.client.execute_async(query)
          is_finished = tlc.client.wait_for_finished_timeout(handle, timeout=60)
          assert is_finished, "Query timeout(60s): " + query
          tlc.client.close_query(handle)
      return True

    # Run renames in parallel
    NUM_ITERS = 16
    worker = [None] * (NUM_ITERS + 1)
    for i in range(1, NUM_ITERS + 1):
      worker[i] = pool.apply_async(run_rename, (i,))
    for i in range(1, NUM_ITERS + 1):
      try:
        assert worker[i].get(timeout=100)
      except TimeoutError:
        dump_server_stacktraces()
        assert False, "Timeout in thread run_ddls(%d)" % i

  @SkipIfFS.hbase
  @UniqueDatabase.parametrize(sync_ddl=True)
  def test_alter_hbase_set_column_stats(self, vector, unique_database):
    self.run_test_case('QueryTest/alter-hbase-table-set-column-stats', vector,
        use_db=unique_database, multiple_impalad=self._use_multiple_impalad(vector))

  @SkipIfLocal.hdfs_client
  def test_drop_partition_with_purge(self, unique_database):
    """Verfies whether alter <tbl> drop partition purge actually skips trash"""
    self.client.execute(
        "create table {0}.t1(i int) partitioned by (j int)".format(unique_database))
    # Add two partitions (j=1) and (j=2) to table t1
    self.client.execute("alter table {0}.t1 add partition(j=1)".format(unique_database))
    self.client.execute("alter table {0}.t1 add partition(j=2)".format(unique_database))
    dbpath = "{1}/{0}.db".format(unique_database, WAREHOUSE)
    self.filesystem_client.create_file("{}/t1/j=1/j1.txt".format(dbpath), file_data='j1')
    self.filesystem_client.create_file("{}/t1/j=2/j2.txt".format(dbpath), file_data='j2')
    # Drop the partition (j=1) without purge and make sure it exists in trash
    self.client.execute("alter table {0}.t1 drop partition(j=1)".format(unique_database))
    assert not self.filesystem_client.exists("{}/t1/j=1/j1.txt".format(dbpath))
    assert not self.filesystem_client.exists("{}/t1/j=1".format(dbpath))
    trash = get_trash_path("test-warehouse", unique_database + ".db")
    assert self.filesystem_client.exists('{}/t1/j=1/j1.txt'.format(trash))
    assert self.filesystem_client.exists('{}/t1/j=1'.format(trash))
    # Drop the partition (with purge) and make sure it doesn't exist in trash
    self.client.execute("alter table {0}.t1 drop partition(j=2) purge".format(
      unique_database))
    if not IS_S3 and not IS_ADLS:
      # In S3, deletes are eventual. So even though we dropped the partition, the files
      # belonging to this partition may still be visible for some unbounded time. This
      # happens only with PURGE. A regular DROP TABLE is just a copy of files which is
      # consistent.
      # The ADLS Python client is not strongly consistent, so these files may still be
      # visible after a DROP. (Remove after IMPALA-5335 is resolved)
      assert not self.filesystem_client.exists("{}/t1/j=2/j2.txt".format(dbpath))
      assert not self.filesystem_client.exists("{}/t1/j=2".format(dbpath))
    assert not self.filesystem_client.exists('{}/t1/j=2/j2.txt'.format(trash))
    assert not self.filesystem_client.exists('{}/t1/j=2'.format(trash))

  @UniqueDatabase.parametrize(sync_ddl=True)
  def test_views_ddl(self, vector, unique_database):
    vector.get_value('exec_option')['abort_on_error'] = False
    self.run_test_case('QueryTest/views-ddl', vector, use_db=unique_database,
        multiple_impalad=self._use_multiple_impalad(vector))

  @UniqueDatabase.parametrize()
  def test_view_hints(self, unique_database):
    # Test that plan hints are stored in the view's comment field; this should work
    # regardless of how Hive formats the output.  Getting this to work with the
    # automated test case runner is rather difficult, so verify directly.  There
    # should be two # of each join hint, one for the original text, one for the expanded
    self.client.execute("""
        create view {0}.hints_test as
        select /* +straight_join */ a.* from functional.alltypestiny a
        inner join /* +broadcast */ functional.alltypes b on a.id = b.id
        inner join /* +shuffle */ functional.alltypessmall c on b.id = c.id
        """.format(unique_database))
    results = self.execute_query("describe formatted %s.hints_test" % unique_database)
    sj, bc, shuf = 0, 0, 0
    for row in results.data:
        sj += '-- +straight_join' in row
        bc += '-- +broadcast' in row
        shuf += '-- +shuffle' in row
    assert sj == 2
    assert bc == 2
    assert shuf == 2

    # Test querying the hinted view.
    results = self.execute_query("select count(*) from %s.hints_test" % unique_database)
    assert results.success
    assert len(results.data) == 1
    assert results.data[0] == '8'

    # Test the plan to make sure hints were applied correctly
    plan = self.execute_query("explain select * from %s.hints_test" % unique_database,
        query_options={'explain_level': 0})
    plan_match = """PLAN-ROOT SINK
08:EXCHANGE [UNPARTITIONED]
04:HASH JOIN [INNER JOIN, PARTITIONED]
|--07:EXCHANGE [HASH(c.id)]
|  02:SCAN {filesystem_name} [functional.alltypessmall c]
06:EXCHANGE [HASH(b.id)]
03:HASH JOIN [INNER JOIN, BROADCAST]
|--05:EXCHANGE [BROADCAST]
|  01:SCAN {filesystem_name} [functional.alltypes b]
00:SCAN {filesystem_name} [functional.alltypestiny a]"""
    assert plan_match.format(filesystem_name=FILESYSTEM_NAME) in '\n'.join(plan.data)

  def _verify_describe_view(self, vector, view_name, expected_substr):
    """
    Verify across all impalads that the view 'view_name' has the given substring in its
    expanded SQL.

    If SYNC_DDL is enabled, the verification should complete immediately. Otherwise,
    loops waiting for the expected condition to pass.
    """
    if vector.get_value('exec_option')['sync_ddl']:
      num_attempts = 1
    else:
      num_attempts = 60
    for impalad in ImpalaCluster.get_e2e_test_cluster().impalads:
      client = impalad.service.create_client_from_vector(vector)
      try:
        for attempt in itertools.count(1):
          assert attempt <= num_attempts, "ran out of attempts"
          try:
            result = self.execute_query_expect_success(
                client, "describe formatted %s" % view_name)
            exp_line = [line for line in result.data if 'View Expanded' in line][0]
          except IMPALA_CONNECTION_EXCEPTION as e:
            # In non-SYNC_DDL tests, it's OK to get a "missing view" type error
            # until the metadata propagates.
            exp_line = "Exception: %s" % e
          if expected_substr in exp_line.lower():
            return
          time.sleep(1)
      finally:
        client.close()

  def test_views_describe(self, vector, unique_database):
    # IMPALA-6896: Tests that altered views can be described by all impalads.
    impala_cluster = ImpalaCluster.get_e2e_test_cluster()
    impalads = impala_cluster.impalads
    view_name = "%s.test_describe_view" % unique_database
    first_client = impalads[0].service.create_client_from_vector(vector)
    try:
      # Create a view and verify it's visible.
      self.execute_query_expect_success(first_client,
                                        "create view {0} as "
                                        "select * from functional.alltypes"
                                        .format(view_name))
      self._verify_describe_view(vector, view_name, "select * from functional.alltypes")

      # Alter the view and verify the alter is visible.
      self.execute_query_expect_success(first_client,
                                        "alter view {0} as "
                                        "select * from functional.alltypesagg"
                                        .format(view_name))
      self._verify_describe_view(vector, view_name,
                                 "select * from functional.alltypesagg")
    finally:
      first_client.close()

  @UniqueDatabase.parametrize(sync_ddl=True)
  def test_functions_ddl(self, vector, unique_database):
    self.run_test_case('QueryTest/functions-ddl', vector, use_db=unique_database,
        multiple_impalad=self._use_multiple_impalad(vector))

  @SkipIfLocal.hdfs_client
  def test_create_alter_bulk_partition(self, unique_database):
    # Change the scale depending on the exploration strategy, with 50 partitions this
    # test runs a few minutes, with 10 partitions it takes ~50s for two configurations.
    num_parts = 50 if self.exploration_strategy() == 'exhaustive' else 10
    fq_tbl_name = unique_database + ".part_test_tbl"
    self.client.execute("create table {0}(i int) partitioned by(j int, s string) "
         "location '{1}/{0}'".format(fq_tbl_name, WAREHOUSE))

    # Add some partitions (first batch of two)
    for i in range(num_parts // 5):
      start = time.time()
      self.client.execute(
          "alter table {0} add partition(j={1}, s='{1}')".format(fq_tbl_name, i))
      LOG.info('ADD PARTITION #%d exec time: %s' % (i, time.time() - start))

    # Modify one of the partitions
    self.client.execute("alter table {0} partition(j=1, s='1')"
        " set fileformat parquetfile".format(fq_tbl_name))

    # Alter one partition to a non-existent location twice (IMPALA-741)
    self.filesystem_client.delete_file_dir("tmp/dont_exist1/", recursive=True)
    self.filesystem_client.delete_file_dir("tmp/dont_exist2/", recursive=True)

    self.execute_query_expect_success(self.client,
        "alter table {0} partition(j=1,s='1') set location '{1}/tmp/dont_exist1'"
        .format(fq_tbl_name, WAREHOUSE))
    self.execute_query_expect_success(self.client,
        "alter table {0} partition(j=1,s='1') set location '{1}/tmp/dont_exist2'"
        .format(fq_tbl_name, WAREHOUSE))

    # Add some more partitions
    for i in range(num_parts // 5, num_parts):
      start = time.time()
      self.client.execute(
          "alter table {0} add partition(j={1},s='{1}')".format(fq_tbl_name, i))
      LOG.info('ADD PARTITION #%d exec time: %s' % (i, time.time() - start))

    # Insert data and verify it shows up.
    self.client.execute(
        "insert into table {0} partition(j=1, s='1') select 1".format(fq_tbl_name))
    assert '1' == self.execute_scalar("select count(*) from {0}".format(fq_tbl_name))

  @SkipIfLocal.hdfs_client
  def test_alter_table_set_fileformat(self, unique_database):
    # Tests that SET FILEFORMAT clause is set for ALTER TABLE ADD PARTITION statement
    fq_tbl_name = unique_database + ".p_fileformat"
    self.client.execute(
        "create table {0}(i int) partitioned by (p int)".format(fq_tbl_name))

    # Add a partition with Parquet fileformat
    self.execute_query_expect_success(self.client,
        "alter table {0} add partition(p=1) set fileformat parquet"
        .format(fq_tbl_name))

    # Add two partitions with ORC fileformat
    self.execute_query_expect_success(self.client,
        "alter table {0} add partition(p=2) partition(p=3) set fileformat orc"
        .format(fq_tbl_name))

    result = self.execute_query_expect_success(self.client,
        "SHOW PARTITIONS %s" % fq_tbl_name)

    assert 1 == len([line for line in result.data if line.find("PARQUET") != -1])
    assert 2 == len([line for line in result.data if line.find("ORC") != -1])

  def test_alter_table_create_many_partitions(self, unique_database):
    """
    Checks that creating more partitions than the MAX_PARTITION_UPDATES_PER_RPC
    batch size works, in that it creates all the underlying partitions.
    """
    self.client.execute(
        "create table {0}.t(i int) partitioned by (p int)".format(unique_database))
    MAX_PARTITION_UPDATES_PER_RPC = 500
    alter_stmt = "alter table {0}.t add ".format(unique_database) + " ".join(
        "partition(p=%d)" % (i,) for i in range(MAX_PARTITION_UPDATES_PER_RPC + 2))
    self.client.execute(alter_stmt)
    partitions = self.client.execute("show partitions {0}.t".format(unique_database))
    # Show partitions will contain partition HDFS paths, which we expect to contain
    # "p=val" subdirectories for each partition. The regexp finds all the "p=[0-9]*"
    # paths, converts them to integers, and checks that wehave all the ones we
    # expect.
    PARTITION_RE = re.compile("p=([0-9]+)")
    assert list(map(int, PARTITION_RE.findall(str(partitions.data)))) == \
        list(range(MAX_PARTITION_UPDATES_PER_RPC + 2))

  def test_create_alter_tbl_properties(self, unique_database):
    fq_tbl_name = unique_database + ".test_alter_tbl"

    # Specify TBLPROPERTIES and SERDEPROPERTIES at CREATE time
    self.client.execute("""create table {0} (i int)
    with serdeproperties ('s1'='s2', 's3'='s4')
    tblproperties ('p1'='v0', 'p1'='v1')""".format(fq_tbl_name))
    properties = self._get_tbl_properties(fq_tbl_name)

    if HIVE_MAJOR_VERSION > 2:
      assert properties['OBJCAPABILITIES'] == 'EXTREAD,EXTWRITE'
      assert properties['TRANSLATED_TO_EXTERNAL'] == 'TRUE'
      assert properties['external.table.purge'] == 'TRUE'
      assert properties['EXTERNAL'] == 'TRUE'
      del properties['OBJCAPABILITIES']
      del properties['TRANSLATED_TO_EXTERNAL']
      del properties['external.table.purge']
      del properties['EXTERNAL']
    assert len(properties) == 2
    # The transient_lastDdlTime is variable, so don't verify the value.
    assert 'transient_lastDdlTime' in properties
    del properties['transient_lastDdlTime']
    assert {'p1': 'v1'} == properties

    properties = self._get_serde_properties(fq_tbl_name)
    assert {'s1': 's2', 's3': 's4'} == properties

    # Modify the SERDEPROPERTIES using ALTER TABLE SET.
    self.client.execute("alter table {0} set serdeproperties "
        "('s1'='new', 's5'='s6')".format(fq_tbl_name))
    properties = self._get_serde_properties(fq_tbl_name)
    assert {'s1': 'new', 's3': 's4', 's5': 's6'} == properties

    # Modify the TBLPROPERTIES using ALTER TABLE SET.
    self.client.execute("alter table {0} set tblproperties "
        "('prop1'='val1', 'p2'='val2', 'p2'='val3', ''='')".format(fq_tbl_name))
    properties = self._get_tbl_properties(fq_tbl_name)

    if HIVE_MAJOR_VERSION > 2:
      assert 'OBJCAPABILITIES' in properties
    assert 'transient_lastDdlTime' in properties
    assert properties['p1'] == 'v1'
    assert properties['prop1'] == 'val1'
    assert properties['p2'] == 'val3'
    assert properties[''] == ''

  @SkipIfHive2.acid
  def test_create_insertonly_tbl(self, unique_database):
    insertonly_tbl = unique_database + ".test_insertonly"
    self.client.execute("""create table {0} (coli int) stored as parquet tblproperties(
        'transactional'='true', 'transactional_properties'='insert_only')"""
        .format(insertonly_tbl))
    properties = self._get_tbl_properties(insertonly_tbl)
    assert properties['OBJCAPABILITIES'] == 'HIVEMANAGEDINSERTREAD,HIVEMANAGEDINSERTWRITE'

  def test_alter_tbl_properties_reload(self, unique_database):
    # IMPALA-8734: Force a table schema reload when setting table properties.
    tbl_name = "test_tbl"
    self.execute_query_expect_success(self.client, "create table {0}.{1} (c1 string)"
                                      .format(unique_database, tbl_name))
    self.filesystem_client.create_file("{2}/{0}.db/{1}/f".
                                       format(unique_database, tbl_name, WAREHOUSE),
                                       file_data="\nfoo\n")
    self.execute_query_expect_success(self.client,
                                      "alter table {0}.{1} set tblproperties"
                                      "('serialization.null.format'='foo')"
                                      .format(unique_database, tbl_name))
    result = self.execute_query_expect_success(self.client,
                                               "select * from {0}.{1}"
                                               .format(unique_database, tbl_name))
    assert len(result.data) == 2
    assert result.data[0] == ''
    assert result.data[1] == 'NULL'

  @SkipIfFS.incorrent_reported_ec
  @UniqueDatabase.parametrize(sync_ddl=True)
  def test_partition_ddl_predicates(self, vector, unique_database):
    self.run_test_case('QueryTest/partition-ddl-predicates-all-fs', vector,
        use_db=unique_database, multiple_impalad=self._use_multiple_impalad(vector))
    if IS_HDFS:
      self.run_test_case('QueryTest/partition-ddl-predicates-hdfs-only', vector,
          use_db=unique_database, multiple_impalad=self._use_multiple_impalad(vector))

  def test_create_table_file_format(self, unique_database):
    # When default_file_format query option is not specified, the default table file
    # format is TEXT.
    text_table = "{0}.text_tbl".format(unique_database)
    self.execute_query_expect_success(
        self.client, "create table {0}(i int)".format(text_table))
    result = self.execute_query_expect_success(
        self.client, "show create table {0}".format(text_table))
    assert any("TEXTFILE" in x for x in result.data)

    self.execute_query_expect_failure(
        self.client, "create table {0}.foobar_tbl".format(unique_database),
        {"default_file_format": "foobar"})

    parquet_table = "{0}.parquet_tbl".format(unique_database)
    self.execute_query_expect_success(
        self.client, "create table {0}(i int)".format(parquet_table),
        {"default_file_format": "parquet"})
    result = self.execute_query_expect_success(
        self.client, "show create table {0}".format(parquet_table))
    assert any("PARQUET" in x for x in result.data)

    # The table created should still be ORC even though the default_file_format query
    # option is set to parquet.
    orc_table = "{0}.orc_tbl".format(unique_database)
    self.execute_query_expect_success(
        self.client,
        "create table {0}(i int) stored as orc".format(orc_table),
        {"default_file_format": "parquet"})
    result = self.execute_query_expect_success(
      self.client, "show create table {0}".format(orc_table))
    assert any("ORC" in x for x in result.data)

  @SkipIfHive2.acid
  def test_create_table_transactional_type(self, unique_database):
    # When default_transactional_type query option is not specified, the transaction
    # related table properties are not set.
    non_acid_table = "{0}.non_acid_tbl".format(unique_database)
    self.execute_query_expect_success(
        self.client, "create table {0}(i int)".format(non_acid_table),
        {"default_transactional_type": "none"})
    props = self._get_properties("Table Parameters", non_acid_table)
    assert "transactional" not in props
    assert "transactional_properties" not in props

    # Create table as "insert_only" transactional.
    insert_only_acid_table = "{0}.insert_only_acid_tbl".format(unique_database)
    self.execute_query_expect_success(
        self.client, "create table {0}(i int)".format(insert_only_acid_table),
        {"default_transactional_type": "insert_only"})
    props = self._get_properties("Table Parameters", insert_only_acid_table)
    assert props["transactional"] == "true"
    assert props["transactional_properties"] == "insert_only"

    # default_transactional_type query option should not affect external tables
    external_table = "{0}.external_tbl".format(unique_database)
    self.execute_query_expect_success(
        self.client, "create external table {0}(i int)".format(external_table),
        {"default_transactional_type": "insert_only"})
    props = self._get_properties("Table Parameters", external_table)
    assert "transactional" not in props
    assert "transactional_properties" not in props

    # default_transactional_type query option should not affect Kudu tables.
    kudu_table = "{0}.kudu_tbl".format(unique_database)
    self.execute_query_expect_success(
        self.client,
        "create table {0}(i int primary key) stored as kudu".format(kudu_table),
        {"default_transactional_type": "insert_only"})
    props = self._get_properties("Table Parameters", kudu_table)
    assert "transactional" not in props
    assert "transactional_properties" not in props

    # default_transactional_type query option should have no effect when transactional
    # table properties are set manually.
    manual_acid_table = "{0}.manual_acid_tbl".format(unique_database)
    self.execute_query_expect_success(
        self.client, "create table {0}(i int) TBLPROPERTIES ('transactional'='false')"
            .format(manual_acid_table),
        {"default_transactional_type": "insert_only"})
    props = self._get_properties("Table Parameters", manual_acid_table)
    assert "transactional" not in props
    assert "transactional_properties" not in props

  def test_kudu_column_comment(self, unique_database):
    table = "{0}.kudu_table0".format(unique_database)
    self.client.execute("create table {0}(x int comment 'x' primary key) \
                        stored as kudu".format(table))
    comment = self._get_column_comment(table, 'x')
    assert "x" == comment

    table = "{0}.kudu_table".format(unique_database)
    self.client.execute("create table {0}(i int primary key) stored as kudu"
                        .format(table))
    comment = self._get_column_comment(table, 'i')
    assert "" == comment

    self.client.execute("comment on column {0}.i is 'comment1'".format(table))
    comment = self._get_column_comment(table, 'i')
    assert "comment1" == comment

    self.client.execute("comment on column {0}.i is ''".format(table))
    comment = self._get_column_comment(table, 'i')
    assert "" == comment

    self.client.execute("comment on column {0}.i is 'comment2'".format(table))
    comment = self._get_column_comment(table, 'i')
    assert "comment2" == comment

    self.client.execute("comment on column {0}.i is null".format(table))
    comment = self._get_column_comment(table, 'i')
    assert "" == comment

    self.client.execute("alter table {0} alter column i set comment 'comment3'"
                        .format(table))
    comment = self._get_column_comment(table, 'i')
    assert "comment3" == comment

    self.client.execute("alter table {0} alter column i set comment ''".format(table))
    comment = self._get_column_comment(table, 'i')
    assert "" == comment

    self.client.execute("alter table {0} add columns (j int comment 'comment4')"
                        .format(table))
    comment = self._get_column_comment(table, 'j')
    assert "comment4" == comment

  @UniqueDatabase.parametrize(sync_ddl=True)
  def test_describe_materialized_view(self, vector, unique_database):
    vector.get_value('exec_option')['abort_on_error'] = False
    self.run_test_case('QueryTest/describe-materialized-view', vector,
        use_db=unique_database, multiple_impalad=self._use_multiple_impalad(vector))


# IMPALA-10811: RPC to submit query getting stuck for AWS NLB forever
# Test HS2, Beeswax and HS2-HTTP three clients.
class TestAsyncDDL(TestDdlBase):
  @classmethod
  def add_test_dimensions(cls):
    super(TestAsyncDDL, cls).add_test_dimensions()
    cls.ImpalaTestMatrix.add_dimension(create_client_protocol_dimension())
    cls.ImpalaTestMatrix.add_dimension(create_exec_option_dimension(
        sync_ddl=[0], disable_codegen_options=[False]))

  def test_async_ddl(self, vector, unique_database):
    self.run_test_case('QueryTest/async_ddl', vector, use_db=unique_database)

  def test_async_ddl_with_JDBC(self, unique_database):
    self.exec_with_jdbc("drop table if exists {0}.test_table".format(unique_database))
    self.exec_with_jdbc_and_compare_result(
        "create table {0}.test_table(a int)".format(unique_database),
        "'Table has been created.'")

    self.exec_with_jdbc("drop table if exists {0}.alltypes_clone".format(unique_database))
    self.exec_with_jdbc_and_compare_result(
        "create table {0}.alltypes_clone as select * from\
        functional_parquet.alltypes".format(unique_database),
        "'Inserted 7300 row(s)'")

  @classmethod
  def test_get_operation_status_for_client(self, client, unique_database):
    # Setup
    client.execute("drop table if exists {0}.alltypes_clone".format(unique_database))
    client.execute("select count(*) from functional_parquet.alltypes")
    client.execute("set enable_async_ddl_execution=true")
    client.execute("set debug_action=\"CRS_DELAY_BEFORE_CATALOG_OP_EXEC:SLEEP@10000\"")

    # Run the test query which will only compile the DDL in execute_statement()
    # and measure the time spent. Should be less than 3s.
    start = time.time()
    handle = client.execute_async(
        "create table {0}.alltypes_clone as select * from \
        functional_parquet.alltypes".format(unique_database))
    end = time.time()
    assert (end - start <= 3)

    # The table creation and population part will be done in a separate thread.
    # The repeated call below to get_operation_status() finds out the number of
    # times that each state is reached in BE for that part of the work.
    num_times_in_initialized_state = 0
    num_times_in_pending_state = 0
    num_times_in_running_state = 0
    while not client.state_is_finished(handle):

      state = client.get_impala_exec_state(handle)

      if (state == INITIALIZED):
        num_times_in_initialized_state += 1

      if (state == PENDING):
        num_times_in_pending_state += 1

      if (state == RUNNING):
        num_times_in_running_state += 1

    # The query must reach INITIALIZED_STATE 0 time and PENDING_STATE at least
    # once. The number of times in PENDING_STATE is a function of the length of
    # the delay. The query reaches RUNNING_STATE when it populates the new table.
    assert num_times_in_initialized_state == 0
    assert num_times_in_pending_state > 1
    assert num_times_in_running_state > 0

  def test_get_operation_status_for_async_ddl(self, vector, unique_database):
    """Tests that for an asynchronously executed DDL with delay, GetOperationStatus
    must be issued repeatedly. Test client hs2-http, hs2 and beeswax"""
    client = self.default_impala_client(vector.get_value('protocol'))
    self.test_get_operation_status_for_client(client, unique_database)


class TestAsyncDDLTiming(TestDdlBase):
  @classmethod
  def add_test_dimensions(cls):
    super(TestAsyncDDLTiming, cls).add_test_dimensions()
    cls.ImpalaTestMatrix.add_dimension(create_client_protocol_dimension())
    cls.ImpalaTestMatrix.add_dimension(create_exec_option_dimension(
        sync_ddl=[0], disable_codegen_options=[False]))
    cls.ImpalaTestMatrix.add_dimension(
        ImpalaTestDimension('enable_async_ddl_execution', True, False))

  def test_alter_table_recover(self, vector, unique_database):
    enable_async_ddl = vector.get_value('enable_async_ddl_execution')
    client = self.create_impala_client(protocol=vector.get_value('protocol'))

    try:
      # Setup for the alter table case (create table that points to an existing
      # location)
      alltypes_location = get_fs_path("/test-warehouse/alltypes_parquet")
      source_tbl = "functional_parquet.alltypes"
      dest_tbl = "{0}.alltypes_clone".format(unique_database)
      create_table_stmt = 'create external table {0} like {1} location "{2}"'.format(
          dest_tbl, source_tbl, alltypes_location)
      self.execute_query_expect_success(client, create_table_stmt)

      # Describe the table to fetch its metadata
      self.execute_query_expect_success(client, "describe {0}".format(dest_tbl))

      # Configure whether to use async DDL and add appropriate delays
      new_vector = deepcopy(vector)
      new_vector.get_value('exec_option')['enable_async_ddl_execution'] = enable_async_ddl
      new_vector.get_value('exec_option')['debug_action'] = \
          "CRS_DELAY_BEFORE_CATALOG_OP_EXEC:SLEEP@10000"
      exec_start = time.time()
      alter_stmt = "alter table {0} recover partitions".format(dest_tbl)
      handle = self.execute_query_async_using_client(client, alter_stmt, new_vector)
      exec_end = time.time()
      exec_time = exec_end - exec_start
      state = client.get_impala_exec_state(handle)
      if enable_async_ddl:
        assert state in [PENDING, RUNNING]
      else:
        assert state in [RUNNING, FINISHED]

      # Wait for the statement to finish with a timeout of 20 seconds
      wait_start = time.time()
      client.wait_for_impala_state(handle, FINISHED, 20)
      wait_end = time.time()
      wait_time = wait_end - wait_start
      self.close_query_using_client(client, handle)
      # In sync mode:
      #  The entire DDL is processed in the exec step with delay. exec_time should be
      #  more than 10 seconds.
      #
      # In async mode:
      #  The compilation of DDL is processed in the exec step without delay. And the
      #  processing of the DDL plan is in wait step with delay. The wait time should
      #  definitely take more time than 10 seconds.
      if enable_async_ddl:
        assert(wait_time >= 10)
      else:
        assert(exec_time >= 10)
    finally:
      client.close()

  def test_ctas(self, vector, unique_database):
    enable_async_ddl = vector.get_value('enable_async_ddl_execution')
    client = self.create_impala_client(protocol=vector.get_value('protocol'))

    try:
      # The CTAS is going to need the metadata of the source table in the
      # select. To avoid flakiness about metadata loading, this selects from
      # that source table first to get the metadata loaded.
      self.execute_query_expect_success(client,
          "select count(*) from functional_parquet.alltypes")

      # Configure whether to use async DDL and add appropriate delays
      new_vector = deepcopy(vector)
      new_vector.get_value('exec_option')['enable_async_ddl_execution'] = enable_async_ddl
      create_delay = "CRS_DELAY_BEFORE_CATALOG_OP_EXEC:SLEEP@10000"
      insert_delay = "CRS_BEFORE_COORD_STARTS:SLEEP@2000"
      new_vector.get_value('exec_option')['debug_action'] = \
          "{0}|{1}".format(create_delay, insert_delay)
      dest_tbl = "{0}.ctas_test".format(unique_database)
      source_tbl = "functional_parquet.alltypes"
      ctas_stmt = 'create external table {0} as select * from {1}'.format(
          dest_tbl, source_tbl)
      exec_start = time.time()
      handle = self.execute_query_async_using_client(client, ctas_stmt, new_vector)
      exec_end = time.time()
      exec_time = exec_end - exec_start
      # The CRS_BEFORE_COORD_STARTS delay postpones the transition from PENDING
      # to RUNNING, so the sync case should be in PENDING state at the end of
      # the execute call. This means that the sync and async cases are the same.
      assert client.is_pending(handle)

      # Wait for the statement to finish with a timeout of 40 seconds
      # (60 seconds without shortcircuit reads). There are other tests running
      # in parallel and ASAN can be slow, so this timeout has been bumped
      # substantially to avoid flakiness. The actual test case does not depend
      # on the statement finishing in a particular amount of time.
      wait_time = 40 if IS_HDFS else 60
      wait_start = time.time()
      client.wait_for_impala_state(handle, FINISHED, wait_time)
      wait_end = time.time()
      wait_time = wait_end - wait_start
      self.close_query_using_client(client, handle)
      # In sync mode:
      #  The entire CTAS is processed in the exec step with delay. exec_time should be
      #  more than 10 seconds.
      #
      # In async mode:
      #  The compilation of CTAS is processed in the exec step without delay. And the
      #  processing of the CTAS plan is in wait step with delay. The wait time should
      #  definitely take more time than 10 seconds.
      if enable_async_ddl:
        assert(wait_time >= 10)
      else:
        assert(exec_time >= 10)
    finally:
      client.close()


class TestDdlLogs(TestDdlBase):
  @classmethod
  def add_test_dimensions(cls):
    super(TestDdlLogs, cls).add_test_dimensions()
    cls.ImpalaTestMatrix.add_dimension(create_exec_option_dimension_from_dict({
        'enable_async_ddl_execution': [True, False]}))

  @SkipIfDockerizedCluster.daemon_logs_not_exposed
  def test_error_logs(self, vector, unique_database):
    query_opts = vector.get_value('exec_option')
    tbl_name = 'test_async' if query_opts['enable_async_ddl_execution'] else 'test_sync'
    tbl_name = unique_database + '.' + tbl_name
    result = self.execute_query_expect_failure(
        self.client, 'invalidate metadata ' + tbl_name, query_opts)
    err = "TableNotFoundException: Table not found: " + tbl_name
    assert err in str(result)
    self.assert_impalad_log_contains('INFO', err)


# IMPALA-2002: Tests repeated adding/dropping of .jar and .so in the lib cache.
class TestLibCache(TestDdlBase):
  @classmethod
  def add_test_dimensions(cls):
    super(TestLibCache, cls).add_test_dimensions()
    cls.ImpalaTestMatrix.add_dimension(create_single_exec_option_dimension())

  def test_create_drop_function(self, vector, unique_database):
    """This will create, run, and drop the same function repeatedly, exercising the
    lib cache mechanism.
    """
    create_fn_stmt = ("create function {0}.f() returns int "
                      "location '{1}/libTestUdfs.so' symbol='NoArgs'"
                      .format(unique_database, WAREHOUSE))
    select_stmt = ("select {0}.f() from functional.alltypes limit 10"
                   .format(unique_database))
    drop_fn_stmt = "drop function %s {0}.f()".format(unique_database)
    self.create_drop_ddl(vector, [create_fn_stmt], [drop_fn_stmt], select_stmt)

  # Run serially because this test inspects global impalad metrics.
  # TODO: The metrics checks could be relaxed to enable running this test in
  # parallel, but that might need a more general wait_for_metric_value().
  @pytest.mark.execute_serially
  def test_create_drop_data_src(self, vector, unique_database):
    """This will create, run, and drop the same data source repeatedly, exercising
    the lib cache mechanism.
    """
    data_src_name = unique_database + "_datasrc"
    create_ds_stmt = ("CREATE DATA SOURCE {0} "
        "LOCATION '{1}/data-sources/test-data-source.jar' "
        "CLASS 'org.apache.impala.extdatasource.AllTypesDataSource' "
        "API_VERSION 'V1'".format(data_src_name, WAREHOUSE))
    create_tbl_stmt = ("CREATE TABLE {0}.data_src_tbl (x int) "
        "PRODUCED BY DATA SOURCE {1}('dummy_init_string')")\
        .format(unique_database, data_src_name)
    drop_ds_stmt = "drop data source %s {0}".format(data_src_name)
    drop_tbl_stmt = "drop table %s {0}.data_src_tbl".format(unique_database)
    select_stmt = "select * from {0}.data_src_tbl limit 1".format(unique_database)
    class_cache_hits_metric = "external-data-source.class-cache.hits"
    class_cache_misses_metric = "external-data-source.class-cache.misses"

    create_stmts = [create_ds_stmt, create_tbl_stmt]
    drop_stmts = [drop_tbl_stmt, drop_ds_stmt]

    # The ImpaladService is used to capture metrics
    service = self.impalad_test_service

    # Initial metric values
    class_cache_hits = service.get_metric_value(class_cache_hits_metric)
    class_cache_misses = service.get_metric_value(class_cache_misses_metric)
    # Test with 1 node so we can check the metrics on only the coordinator
    vector.get_value('exec_option')['num_nodes'] = 1
    num_iterations = 2
    self.create_drop_ddl(vector, create_stmts, drop_stmts, select_stmt, num_iterations)

    # Check class cache metrics. Shouldn't have any new cache hits, there should be
    # 2 cache misses for every iteration (jar is loaded by both the FE and BE).
    expected_cache_misses = class_cache_misses + (num_iterations * 2)
    service.wait_for_metric_value(class_cache_hits_metric, class_cache_hits)
    service.wait_for_metric_value(class_cache_misses_metric,
        expected_cache_misses)

    # Test with a table that caches the class
    create_tbl_stmt = ("CREATE TABLE {0}.data_src_tbl (x int) "
        "PRODUCED BY DATA SOURCE {1}('CACHE_CLASS::dummy_init_string')")\
        .format(unique_database, data_src_name)
    create_stmts = [create_ds_stmt, create_tbl_stmt]
    # Run once before capturing metrics because the class already may be cached from
    # a previous test run.
    # TODO: Provide a way to clear the cache
    self.create_drop_ddl(vector, create_stmts, drop_stmts, select_stmt, 1)

    # Capture metric values and run again, should hit the cache.
    class_cache_hits = service.get_metric_value(class_cache_hits_metric)
    class_cache_misses = service.get_metric_value(class_cache_misses_metric)
    self.create_drop_ddl(vector, create_stmts, drop_stmts, select_stmt, 1)
    service.wait_for_metric_value(class_cache_hits_metric, class_cache_hits + 2)
    service.wait_for_metric_value(class_cache_misses_metric, class_cache_misses)

  def create_drop_ddl(self, vector, create_stmts, drop_stmts, select_stmt,
      num_iterations=3):
    """Helper method to run CREATE/DROP DDL commands repeatedly and exercise the lib
    cache. create_stmts is the list of CREATE statements to be executed in order
    drop_stmts is the list of DROP statements to be executed in order. Each statement
    should have a '%s' placeholder to insert "IF EXISTS" or "". The select_stmt is just a
    single statement to test after executing the CREATE statements.
    TODO: it's hard to tell that the cache is working (i.e. if it did nothing to drop
    the cache, these tests would still pass). Testing that is a bit harder and requires
    us to update the udf binary in the middle.
    """
    self.client.set_configuration(vector.get_value("exec_option"))
    for drop_stmt in drop_stmts: self.client.execute(drop_stmt % ("if exists"))
    for i in range(0, num_iterations):
      for create_stmt in create_stmts: self.client.execute(create_stmt)
      self.client.execute(select_stmt)
      for drop_stmt in drop_stmts: self.client.execute(drop_stmt % (""))
