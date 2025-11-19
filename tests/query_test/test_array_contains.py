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

from tests.common.impala_test_suite import ImpalaTestSuite
from tests.common.test_dimensions import (
    add_exec_option_dimension,
    create_exec_option_dimension_from_dict,
    create_client_protocol_dimension,
    orc_schema_resolution_constraint)

ORC_RESOLUTION_DIMS = [0, 1]

class TestArrayContains(ImpalaTestSuite):
  """Functional tests for array_contains function."""
  @classmethod
  def add_test_dimensions(cls):
    super(TestArrayContains, cls).add_test_dimensions()
    cls.ImpalaTestMatrix.add_dimension(
        create_exec_option_dimension_from_dict({
            'disable_codegen': ['False', 'True'],
            # The below two options are set to prevent the planner from disabling codegen
            # because of the small data size even when 'disable_codegen' is False.
            'disable_codegen_rows_threshold': [0],
            'exec_single_node_rows_threshold': [0]}))
    # Must declare 'orc_schema_resolution' using 'add_exec_option_dimension' so that
    # 'orc_schema_resolution_constraint' can catch it.
    add_exec_option_dimension(cls, 'orc_schema_resolution', ORC_RESOLUTION_DIMS)
    cls.ImpalaTestMatrix.add_dimension(create_client_protocol_dimension())
    cls.ImpalaTestMatrix.add_constraint(lambda v:
        v.get_value('table_format').file_format in ['parquet', 'orc'])
    cls.ImpalaTestMatrix.add_constraint(orc_schema_resolution_constraint)

  def test_array_contains(self, vector):
    """Queries that test array_contains function"""
    self.run_test_case('QueryTest/array-contains', vector)
