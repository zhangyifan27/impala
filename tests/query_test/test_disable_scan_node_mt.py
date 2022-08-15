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

from tests.common.impala_test_suite import ImpalaTestSuite
from tests.common.skip import (SkipIfEC, SkipIfLocal, SkipIfS3, SkipIfABFS,
                               SkipIfGCS, SkipIfCOS, SkipIfADLS)
from tests.common.test_dimensions import create_kudu_dimension
from tests.common.test_dimensions import create_parquet_dimension
from tests.common.test_dimensions import create_uncompressed_text_dimension


class TestDisableHdfsScanNodeMt(ImpalaTestSuite):
  """Test disable HdfsScanNodeMt functionality."""

  @classmethod
  def get_workload(self):
    return 'functional-query'

  @classmethod
  def add_test_dimensions(cls):
    super(TestDisableHdfsScanNodeMt, cls).add_test_dimensions()
    cls.ImpalaTestMatrix.add_dimension(
        create_parquet_dimension(cls.get_workload()))

  def test_disable_scan_node_mt(self, vector):
    self.run_test_case('QueryTest/disable-scan-node-mt', vector)


class TestDisableKuduScanNodeMt(ImpalaTestSuite):
  """Test disable KuduScanNodeMt functionality."""

  @classmethod
  def get_workload(self):
    return 'functional-query'

  @classmethod
  def add_test_dimensions(cls):
    super(TestDisableKuduScanNodeMt, cls).add_test_dimensions()
    cls.ImpalaTestMatrix.add_dimension(
        create_kudu_dimension(cls.get_workload()))

  def test_disable_scan_node_mt(self, vector):
    self.run_test_case('QueryTest/disable-scan-node-mt', vector)


class TestDisableHdfsScanNodeMtWithTextFile(ImpalaTestSuite):
  """Test disable HdfsScanNodeMt with text file. We may get more instances than files 
  in some cases, test that we can execute query successfully and get right result."""

  @classmethod
  def get_workload(self):
    return 'tpch'

  @classmethod
  def add_test_dimensions(cls):
    super(TestDisableHdfsScanNodeMtWithTextFile, cls).add_test_dimensions()
    cls.ImpalaTestMatrix.add_dimension(
        create_uncompressed_text_dimension(cls.get_workload()))

  def test_disable_scan_node_mt_with_text_file(self, vector):
    query = "select count(*) from tpch.lineitem;"
    vector.get_value('exec_option')['disable_scan_node_mt'] = 1
    vector.get_value('exec_option')['mt_dop'] = 3
    results = self.execute_query(query, vector.get_value('exec_option'))
    assert results.success
    assert len(results.data) == 1
    assert int(results.data[0]) == 6001215
