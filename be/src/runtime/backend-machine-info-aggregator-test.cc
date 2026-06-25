// Licensed to the Apache Software Foundation (ASF) under one
// or more contributor license agreements.  See the NOTICE file
// distributed with this work for additional information
// regarding copyright ownership.  The ASF licenses this file
// to you under the Apache License, Version 2.0 (the
// "License"); you may not use this file except in compliance
// with the License.  You may obtain a copy of the License at
//
//   http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing,
// software distributed under the License is distributed on an
// "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
// KIND, either express or implied.  See the License for the
// specific language governing permissions and limitations
// under the License.

#include "runtime/backend-machine-info-aggregator.h"

#include "testutil/gtest-util.h"
#include "gen-cpp/admission_control_service.pb.h"
#include "gen-cpp/statestore_service.pb.h"

namespace impala {

class MachineInfoPbStringTest : public testing::Test {};

TEST_F(MachineInfoPbStringTest, EmptyProto) {
  MachineInfoPB m;
  EXPECT_EQ("Unknown",
      BackendMachineInfoAggregator::MachineInfoPBToCpuModelDisplayString(m));
  EXPECT_EQ("Unknown (unknown cores)",
      BackendMachineInfoAggregator::MachineInfoPBToCpuConfigString(m));
  EXPECT_EQ("Unknown", BackendMachineInfoAggregator::MachineInfoPBToOsDisplayString(m));
}

TEST_F(MachineInfoPbStringTest, FullProto) {
  MachineInfoPB m;
  m.set_cpu_model_name("Intel(R) Xeon(R) CPU E5-2680 v4 @ 2.40GHz");
  m.set_cpu_num_cores(28);
  m.set_os_distribution("CentOS Linux 7");

  EXPECT_EQ("Intel(R) Xeon(R) CPU E5-2680 v4 @ 2.40GHz",
      BackendMachineInfoAggregator::MachineInfoPBToCpuModelDisplayString(m));
  EXPECT_EQ("Intel(R) Xeon(R) CPU E5-2680 v4 @ 2.40GHz (28 cores)",
      BackendMachineInfoAggregator::MachineInfoPBToCpuConfigString(m));
  EXPECT_EQ("CentOS Linux 7",
      BackendMachineInfoAggregator::MachineInfoPBToOsDisplayString(m));
}

TEST_F(MachineInfoPbStringTest, ModelOnly) {
  MachineInfoPB m;
  m.set_cpu_model_name("Intel(R) Xeon(R) CPU E5-2680 v4 @ 2.40GHz");

  EXPECT_EQ("Intel(R) Xeon(R) CPU E5-2680 v4 @ 2.40GHz (unknown cores)",
      BackendMachineInfoAggregator::MachineInfoPBToCpuConfigString(m));
  EXPECT_EQ("Unknown", BackendMachineInfoAggregator::MachineInfoPBToOsDisplayString(m));
}

TEST_F(MachineInfoPbStringTest, CoresAndOsOnly) {
  MachineInfoPB m;
  m.set_cpu_num_cores(32);
  m.set_os_distribution("Ubuntu 22.04.5 LTS");

  EXPECT_EQ("Unknown (32 cores)",
      BackendMachineInfoAggregator::MachineInfoPBToCpuConfigString(m));
  EXPECT_EQ("Ubuntu 22.04.5 LTS",
      BackendMachineInfoAggregator::MachineInfoPBToOsDisplayString(m));
}

class BackendMachineInfoAggregatorTest : public testing::Test {};

TEST_F(BackendMachineInfoAggregatorTest, EmptyAggregator) {
  BackendMachineInfoAggregator aggregator;

  EXPECT_FALSE(aggregator.HasData());
  EXPECT_EQ("", aggregator.GetCpuSummary());
  EXPECT_EQ("", aggregator.GetOsSummary());
}

TEST_F(BackendMachineInfoAggregatorTest, SingleConfig) {
  BackendMachineInfoAggregator aggregator;

  MachineInfoPB m;
  m.set_cpu_model_name("Intel(R) Xeon(R) Silver 4215R CPU @ 3.20GHz");
  m.set_cpu_num_cores(32);
  m.set_os_distribution("Ubuntu 22.04.5 LTS");

  aggregator.Merge(m);
  aggregator.Merge(m);
  aggregator.Merge(m);

  EXPECT_TRUE(aggregator.HasData());
  EXPECT_EQ("Intel(R) Xeon(R) Silver 4215R CPU @ 3.20GHz (32 cores) (3)",
      aggregator.GetCpuSummary());
  EXPECT_EQ("Ubuntu 22.04.5 LTS (3)", aggregator.GetOsSummary());
}

TEST_F(BackendMachineInfoAggregatorTest, MultipleConfigs) {
  BackendMachineInfoAggregator aggregator;

  MachineInfoPB m1;
  m1.set_cpu_model_name("Intel(R) Xeon(R) CPU E5-2680 v4 @ 2.40GHz");
  m1.set_cpu_num_cores(28);
  m1.set_os_distribution("CentOS Linux 7");

  for (int i = 0; i < 15; ++i) {
    aggregator.Merge(m1);
  }

  MachineInfoPB m2;
  m2.set_cpu_model_name("Intel(R) Xeon(R) CPU E5-2660 v3 @ 2.60GHz");
  m2.set_cpu_num_cores(20);
  m2.set_os_distribution("Ubuntu 20.04.3 LTS");

  for (int i = 0; i < 3; ++i) {
    aggregator.Merge(m2);
  }

  EXPECT_TRUE(aggregator.HasData());

  std::string cpu_summary = aggregator.GetCpuSummary();
  EXPECT_NE(std::string::npos, cpu_summary.find("28 cores) (15)"));
  EXPECT_NE(std::string::npos, cpu_summary.find("20 cores) (3)"));

  std::string os_summary = aggregator.GetOsSummary();
  EXPECT_NE(std::string::npos, os_summary.find("CentOS Linux 7 (15)"));
  EXPECT_NE(std::string::npos, os_summary.find("Ubuntu 20.04.3 LTS (3)"));
}

TEST_F(BackendMachineInfoAggregatorTest, PartialInfoStillCounted) {
  BackendMachineInfoAggregator aggregator;

  MachineInfoPB partial;
  partial.set_cpu_model_name("Some CPU");
  // No core count, no OS — still one backend worth of data
  aggregator.Merge(partial);

  EXPECT_TRUE(aggregator.HasData());
  EXPECT_EQ("Some CPU (unknown cores) (1)", aggregator.GetCpuSummary());
  EXPECT_EQ("Unknown (1)", aggregator.GetOsSummary());
}

TEST_F(BackendMachineInfoAggregatorTest, MixedPartialAndFull) {
  BackendMachineInfoAggregator aggregator;

  MachineInfoPB full;
  full.set_cpu_model_name("Intel(R) Xeon(R) Silver 4215R CPU @ 3.20GHz");
  full.set_cpu_num_cores(32);
  full.set_os_distribution("Ubuntu 22.04.5 LTS");

  aggregator.Merge(full);
  aggregator.Merge(full);

  MachineInfoPB partial;
  partial.set_cpu_model_name("Some CPU");

  aggregator.Merge(partial);

  EXPECT_TRUE(aggregator.HasData());
  EXPECT_NE(std::string::npos,
      aggregator.GetCpuSummary().find("Intel(R) Xeon(R) Silver 4215R CPU @ 3.20GHz "
                                      "(32 cores) (2)"));
  EXPECT_NE(std::string::npos,
      aggregator.GetCpuSummary().find("Some CPU (unknown cores) (1)"));
  EXPECT_NE(std::string::npos, aggregator.GetOsSummary().find("Ubuntu 22.04.5 LTS (2)"));
  EXPECT_NE(std::string::npos, aggregator.GetOsSummary().find("Unknown (1)"));
}

TEST_F(BackendMachineInfoAggregatorTest, OrderingDeterministic) {
  BackendMachineInfoAggregator aggregator;

  MachineInfoPB m1;
  m1.set_cpu_model_name("CPU B");
  m1.set_cpu_num_cores(20);
  m1.set_os_distribution("OS B");

  MachineInfoPB m2;
  m2.set_cpu_model_name("CPU A");
  m2.set_cpu_num_cores(28);
  m2.set_os_distribution("OS A");

  aggregator.Merge(m1);
  aggregator.Merge(m2);
  aggregator.Merge(m1);

  std::string cpu_summary = aggregator.GetCpuSummary();
  std::string os_summary = aggregator.GetOsSummary();

  size_t pos_cpu_a = cpu_summary.find("CPU A");
  size_t pos_cpu_b = cpu_summary.find("CPU B");
  EXPECT_NE(std::string::npos, pos_cpu_a);
  EXPECT_NE(std::string::npos, pos_cpu_b);
  EXPECT_LT(pos_cpu_a, pos_cpu_b);

  size_t pos_os_a = os_summary.find("OS A");
  size_t pos_os_b = os_summary.find("OS B");
  EXPECT_NE(std::string::npos, pos_os_a);
  EXPECT_NE(std::string::npos, pos_os_b);
  EXPECT_LT(pos_os_a, pos_os_b);
}

} // namespace impala
