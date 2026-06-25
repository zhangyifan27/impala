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

#pragma once

#include <map>
#include <sstream>
#include <string>

#include "gen-cpp/statestore_service.pb.h"

namespace impala {

/// Aggregates MachineInfoPB values from multiple backends into summary strings for the
/// query profile. Each backend is counted using placeholder strings for any missing
/// field so totals match the number of backends.
class BackendMachineInfoAggregator {
 public:
  /// Display string for the CPU model portion of MachineInfoPB. Missing or
  /// empty values are shown as "Unknown".
  static std::string MachineInfoPBToCpuModelDisplayString(
      const MachineInfoPB& machine_info) {
    if (machine_info.has_cpu_model_name() && !machine_info.cpu_model_name().empty()) {
      return machine_info.cpu_model_name();
    }
    return "Unknown";
  }

  /// Single-line CPU description for profiles, e.g.
  /// "Intel(R) Xeon(R) Silver 4215R CPU @ 3.20GHz (32 cores)" or
  /// "Some Model (unknown cores)" when core count is unset.
  static std::string MachineInfoPBToCpuConfigString(const MachineInfoPB& machine_info) {
    const std::string model = MachineInfoPBToCpuModelDisplayString(machine_info);
    std::stringstream ss;
    ss << model << " (";
    if (machine_info.has_cpu_num_cores()) {
      ss << machine_info.cpu_num_cores() << " cores)";
    } else {
      ss << "unknown cores)";
    }
    return ss.str();
  }

  /// Display string for the OS distribution. Missing or empty values are shown as
  /// "Unknown".
  static std::string MachineInfoPBToOsDisplayString(const MachineInfoPB& machine_info) {
    if (machine_info.has_os_distribution() && !machine_info.os_distribution().empty()) {
      return machine_info.os_distribution();
    }
    return "Unknown";
  }

  void Merge(const MachineInfoPB& machine_info) {
    cpu_configs_[MachineInfoPBToCpuConfigString(machine_info)]++;
    os_configs_[MachineInfoPBToOsDisplayString(machine_info)]++;
  }

  /// Returns a summary string of CPU configurations.
  /// Example: "Intel Xeon E5-2680 (28 cores) (15), Intel Xeon E5-2660 (20 cores) (3)"
  std::string GetCpuSummary() const {
    if (cpu_configs_.empty()) return "";

    std::stringstream ss;
    bool first = true;
    for (const auto& entry : cpu_configs_) {
      if (!first) ss << ", ";
      ss << entry.first << " (" << entry.second << ")";
      first = false;
    }
    return ss.str();
  }

  /// Returns a summary string of OS distributions.
  /// Example: "CentOS Linux 7 (15), Ubuntu 20.04.3 LTS (3)"
  std::string GetOsSummary() const {
    if (os_configs_.empty()) return "";

    std::stringstream ss;
    bool first = true;
    for (const auto& entry : os_configs_) {
      if (!first) ss << ", ";
      ss << entry.first << " (" << entry.second << ")";
      first = false;
    }
    return ss.str();
  }

  /// Returns true if any machine information has been merged.
  bool HasData() const {
    return !cpu_configs_.empty() || !os_configs_.empty();
  }

 private:
  /// Maps CPU configuration string to count of backends with that configuration.
  std::map<std::string, int> cpu_configs_;

  /// Maps OS distribution to count of backends with that OS.
  std::map<std::string, int> os_configs_;
};

} // namespace impala
