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

# Target including all protobuf-generated code.
add_custom_target(kudu-util-proto-deps)

#######################################
# block_bloom_filter_proto
#######################################

PROTOBUF_GENERATE_CPP(
  BLOCK_BLOOM_FILTER_PROTO_SRCS BLOCK_BLOOM_FILTER_PROTO_HDRS BLOCK_BLOOM_FILTER_PROTO_TGTS
  SOURCE_ROOT ${CMAKE_CURRENT_SOURCE_DIR}/../..
  BINARY_ROOT ${CMAKE_CURRENT_BINARY_DIR}/../..
  PROTO_FILES block_bloom_filter.proto)
ADD_EXPORTABLE_LIBRARY(block_bloom_filter_proto
  SRCS ${BLOCK_BLOOM_FILTER_PROTO_SRCS}
  DEPS hash_proto pb_util_proto protobuf
  NONLINK_DEPS ${BLOCK_BLOOM_FILTER_PROTO_TGTS})

add_dependencies(kudu-util-proto-deps ${BLOCK_BLOOM_FILTER_PROTO_TGTS})

#######################################
# util_compression_proto
#######################################

PROTOBUF_GENERATE_CPP(
  UTIL_COMPRESSION_PROTO_SRCS UTIL_COMPRESSION_PROTO_HDRS UTIL_COMPRESSION_PROTO_TGTS
  SOURCE_ROOT ${CMAKE_CURRENT_SOURCE_DIR}/../..
  BINARY_ROOT ${CMAKE_CURRENT_BINARY_DIR}/../..
  PROTO_FILES compression/compression.proto)
ADD_EXPORTABLE_LIBRARY(util_compression_proto
  SRCS ${UTIL_COMPRESSION_PROTO_SRCS}
  DEPS protobuf
  NONLINK_DEPS ${UTIL_COMPRESSION_PROTO_TGTS})

add_dependencies(kudu-util-proto-deps ${UTIL_COMPRESSION_PROTO_TGTS})

add_definitions(-DKUDU_HEADERS_USE_SHORT_STATUS_MACROS)

#######################################
# hash_proto
#######################################

PROTOBUF_GENERATE_CPP(
  HASH_PROTO_SRCS HASH_PROTO_HDRS HASH_PROTO_TGTS
  SOURCE_ROOT ${CMAKE_CURRENT_SOURCE_DIR}/../..
  BINARY_ROOT ${CMAKE_CURRENT_BINARY_DIR}/../..
  PROTO_FILES hash.proto)
ADD_EXPORTABLE_LIBRARY(hash_proto
  SRCS ${HASH_PROTO_SRCS}
  DEPS protobuf
  NONLINK_DEPS ${HASH_PROTO_TGTS})

add_dependencies(kudu-util-proto-deps ${HASH_PROTO_TGTS})

#######################################
# histogram_proto
#######################################

PROTOBUF_GENERATE_CPP(
  HISTOGRAM_PROTO_SRCS HISTOGRAM_PROTO_HDRS HISTOGRAM_PROTO_TGTS
  SOURCE_ROOT ${CMAKE_CURRENT_SOURCE_DIR}/../..
  BINARY_ROOT ${CMAKE_CURRENT_BINARY_DIR}/../..
  PROTO_FILES histogram.proto)
ADD_EXPORTABLE_LIBRARY(histogram_proto
  SRCS ${HISTOGRAM_PROTO_SRCS}
  DEPS protobuf
  NONLINK_DEPS ${HISTOGRAM_PROTO_TGTS})

add_dependencies(kudu-util-proto-deps ${HISTOGRAM_PROTO_TGTS})

#######################################
# maintenance_manager_proto
#######################################

PROTOBUF_GENERATE_CPP(
  MAINTENANCE_MANAGER_PROTO_SRCS MAINTENANCE_MANAGER_PROTO_HDRS MAINTENANCE_MANAGER_PROTO_TGTS
  SOURCE_ROOT ${CMAKE_CURRENT_SOURCE_DIR}/../..
  BINARY_ROOT ${CMAKE_CURRENT_BINARY_DIR}/../..
  PROTO_FILES maintenance_manager.proto)
ADD_EXPORTABLE_LIBRARY(maintenance_manager_proto
  SRCS ${MAINTENANCE_MANAGER_PROTO_SRCS}
  DEPS protobuf
  NONLINK_DEPS ${MAINTENANCE_MANAGER_PROTO_TGTS})

add_dependencies(kudu-util-proto-deps ${MAINTENANCE_MANAGER_PROTO_TGTS})

#######################################
# mem_tracker_proto
#######################################

PROTOBUF_GENERATE_CPP(
  MEM_TRACKER_PROTO_SRCS MEM_TRACKER_PROTO_HDRS MEM_TRACKER_PROTO_TGTS
  SOURCE_ROOT ${CMAKE_CURRENT_SOURCE_DIR}/../..
  BINARY_ROOT ${CMAKE_CURRENT_BINARY_DIR}/../..
  PROTO_FILES mem_tracker.proto)
ADD_EXPORTABLE_LIBRARY(mem_tracker_proto
  SRCS ${MEM_TRACKER_PROTO_SRCS}
  DEPS protobuf
  NONLINK_DEPS ${MEM_TRACKER_PROTO_TGTS})

add_dependencies(kudu-util-proto-deps ${MEM_TRACKER_PROTO_TGTS})

#######################################
# pb_util_proto
#######################################

PROTOBUF_GENERATE_CPP(
  PB_UTIL_PROTO_SRCS PB_UTIL_PROTO_HDRS PB_UTIL_PROTO_TGTS
  SOURCE_ROOT ${CMAKE_CURRENT_SOURCE_DIR}/../..
  BINARY_ROOT ${CMAKE_CURRENT_BINARY_DIR}/../..
  PROTO_FILES pb_util.proto)
ADD_EXPORTABLE_LIBRARY(pb_util_proto
  SRCS ${PB_UTIL_PROTO_SRCS}
  DEPS protobuf
  NONLINK_DEPS ${PB_UTIL_PROTO_TGTS})

add_dependencies(kudu-util-proto-deps ${PB_UTIL_PROTO_TGTS})

#######################################
# version_info_proto
#######################################

PROTOBUF_GENERATE_CPP(
  VERSION_INFO_PROTO_SRCS VERSION_INFO_PROTO_HDRS VERSION_INFO_PROTO_TGTS
  SOURCE_ROOT ${CMAKE_CURRENT_SOURCE_DIR}/../..
  BINARY_ROOT ${CMAKE_CURRENT_BINARY_DIR}/../..
  PROTO_FILES version_info.proto)
ADD_EXPORTABLE_LIBRARY(version_info_proto
  SRCS ${VERSION_INFO_PROTO_SRCS}
  DEPS protobuf
  NONLINK_DEPS ${VERSION_INFO_PROTO_TGTS})

add_dependencies(kudu-util-proto-deps ${VERSION_INFO_PROTO_TGTS})

############################################################
# Version stamp
############################################################

# Unlike CMAKE_CURRENT_BINARY_DIR, CMAKE_BINARY_DIR is always the root of
# the build directory.
set(VERSION_STAMP_FILE ${CMAKE_BINARY_DIR}/src/kudu/generated/version_defines.h)

list(APPEND GEN_VERSION_INFO_COMMAND "${BUILD_SUPPORT_DIR}/gen_version_info.py")
list(APPEND GEN_VERSION_INFO_COMMAND "--version=${KUDU_VERSION_NUMBER}")
list(APPEND GEN_VERSION_INFO_COMMAND "--build-type=${CMAKE_BUILD_TYPE}")
if(KUDU_GIT_HASH)
  message(STATUS "Provided git hash: ${KUDU_GIT_HASH}")
  list(APPEND GEN_VERSION_INFO_COMMAND "--git-hash=${KUDU_GIT_HASH}")
endif()
list(APPEND GEN_VERSION_INFO_COMMAND "${VERSION_STAMP_FILE}")
add_custom_target(gen_version_info
    COMMAND ${GEN_VERSION_INFO_COMMAND}
    BYPRODUCTS "${VERSION_STAMP_FILE}")

#######################################
# kudu_util
#######################################

if (APPLE)
  set(SEMAPHORE_CC "semaphore_macosx.cc")
else ()
  set(SEMAPHORE_CC "semaphore.cc")
endif()

set(UTIL_SRCS
  async_logger.cc
  atomic.cc
  bitmap.cc
  block_cache_metrics.cc
  block_bloom_filter.cc
  bloom_filter.cc
  cache.cc
  # Skipped in Impala builds.
  #char_util.cc
  coding.cc
  condition_variable.cc
  cow_object.cc
  crc.cc
  debug-util.cc
  decimal_util.cc
  debug/trace_event_impl.cc
  debug/trace_event_impl_constants.cc
  debug/trace_event_synthetic_delay.cc
  debug/unwind_safeness.cc
  easy_json.cc
  env.cc env_posix.cc env_util.cc
  errno.cc
  faststring.cc
  fault_injection.cc
  # Skipped in Impala builds.
  #file_cache.cc
  file_cache_metrics.cc
  flags.cc
  flag_tags.cc
  flag_validators.cc
  group_varint.cc
  pstack_watcher.cc
  hdr_histogram.cc
  hexdump.cc
  init.cc
  jsonreader.cc
  jsonwriter.cc
  kernel_stack_watchdog.cc
  locks.cc
  logging.cc
  maintenance_manager.cc
  maintenance_manager_metrics.cc
  malloc.cc
  memcmpable_varint.cc
  memory/arena.cc
  memory/memory.cc
  memory/overwrite.cc
  mem_tracker.cc
  metrics.cc
  # Skipped in Impala builds.
  #minidump.cc
  monotime.cc
  mutex.cc
  net/dns_resolver.cc
  net/net_util.cc
  net/sockaddr.cc
  net/socket.cc
  nvm_cache.cc
  oid_generator.cc
  once.cc
  openssl_util.cc
  os-util.cc
  path_util.cc
  pb_util.cc
  pb_util-internal.cc
  process_memory.cc
  prometheus_writer.cc
  random_util.cc
  rolling_log.cc
  rw_mutex.cc
  rwc_lock.cc
  ${SEMAPHORE_CC}
  signal.cc
  slice.cc
  spinlock_profiling.cc
  status.cc
  status_callback.cc
  string_case.cc
  striped64.cc
  subprocess.cc
  test_util_prod.cc
  thread.cc
  threadlocal.cc
  threadpool.cc
  thread_restrictions.cc
  throttler.cc
  trace.cc
  trace_metrics.cc
  user.cc
  url-coding.cc
  # Remove from compilation, as it depends on generated method calls. Replaced by
  # kudu_version.cc in Impala's common library.
  #version_info.cc
  version_util.cc
  web_callback_registry.cc
  website_util.cc
  # Skipped in Impala builds.
  #yamlreader.cc
  zlib.cc
)

if(NOT NO_TESTS)
  set(UTIL_SRCS ${UTIL_SRCS} test_graph.cc)
endif()

# overwrite.cc contains a single function which would be a hot spot in
# debug builds. It's separated into a separate file so it can be
# optimized regardless of the default optimization options.
set_source_files_properties(memory/overwrite.cc PROPERTIES COMPILE_FLAGS "-O3")

# Detect AVX2 support
execute_process(
  COMMAND echo
  COMMAND ${CMAKE_CXX_COMPILER} -mavx2 -dM -E -
  COMMAND awk "$2 == \"__AVX2__\" { print $3 }"
  ERROR_QUIET
  OUTPUT_VARIABLE AVX2_SUPPORT
  OUTPUT_STRIP_TRAILING_WHITESPACE
)

# block_bloom_filter_avx2.cc uses AVX2 operations.
if (AVX2_SUPPORT)
  list(APPEND UTIL_SRCS block_bloom_filter_avx2.cc)
  set_source_files_properties(block_bloom_filter_avx2.cc PROPERTIES COMPILE_FLAGS "-mavx2")
  # block_bloom_filter.cc is not compiled explicitly with AVX2 instructions(-mavx2) but it needs
  # to know at compile time whether AVX2 support is available, hence the custom definition
  # instead of relying on __AVX2__ defined by compiler with -mavx2.
  set_source_files_properties(block_bloom_filter_avx2.cc block_bloom_filter.cc
                              PROPERTIES COMPILE_DEFINITIONS "USE_AVX2=1")
  message("Compiler supports AVX2")
else()
  message("Compiler does not support AVX2")
endif()

set(UTIL_LIBS
  block_bloom_filter_proto
  crcutil
  gflags
  glog
  gutil
  hash_proto
  histogram_proto
  libev
  maintenance_manager_proto
  mem_tracker_proto
  pb_util_proto
  protobuf
  openssl_crypto
  openssl_ssl
  version_info_proto
  # Skipped in Impala builds.
  #yaml
  zlib)

if(NOT APPLE)
  set(UTIL_LIBS
    ${UTIL_LIBS}
    breakpad_client
    dl
    rt)
endif()

# We use MallocExtension, but not in the exported version of the library.
set(EXPORTED_UTIL_LIBS ${UTIL_LIBS})
if(${KUDU_TCMALLOC_AVAILABLE})
  list(APPEND UTIL_LIBS tcmalloc)
endif()

ADD_EXPORTABLE_LIBRARY(kudu_util
  SRCS ${UTIL_SRCS}
  DEPS ${UTIL_LIBS}
  NONLINK_DEPS gen_version_info
  EXPORTED_DEPS ${EXPORTED_UTIL_LIBS})

#######################################
# kudu_util_compression
#######################################
set(UTIL_COMPRESSION_SRCS
  compression/compression_codec.cc)
set(UTIL_COMPRESSION_LIBS
  kudu_util
  util_compression_proto
  glog
  gutil
  lz4
  snappy
  zlib)

ADD_EXPORTABLE_LIBRARY(kudu_util_compression
  SRCS ${UTIL_COMPRESSION_SRCS}
  DEPS ${UTIL_COMPRESSION_LIBS})
# Define LZ4_DISABLE_DEPRECATE_WARNINGS to mute warnings like:
# "'int LZ4_compress(const char*, char*, int)' is deprecated".
target_compile_definitions(kudu_util_compression PUBLIC LZ4_DISABLE_DEPRECATE_WARNINGS)
# Skipped in Impala builds.
#target_compile_definitions(kudu_util_compression_exported PUBLIC LZ4_DISABLE_DEPRECATE_WARNINGS)

#######################################
# kudu_curl_util
#######################################
add_library(kudu_curl_util
  curl_util.cc)
target_link_libraries(kudu_curl_util
  security
  curl
  glog
  gutil)

#######################################
# kudu_cloud_util
#######################################
# Skipped in Impala builds as Impala doesn't use it.
# add_library(kudu_cloud_util
#   cloud/instance_detector.cc
#   cloud/instance_metadata.cc)
# target_link_libraries(kudu_cloud_util
#   kudu_curl_util)

#######################################
# kudu_jwt_util
#######################################
# Note: JWT support is already available in Impala so we use that.
#add_library(kudu_jwt_util jwt-util.cc)
#target_link_libraries(kudu_jwt_util
#  gutil
#  security
#  kudu_curl_util
#  kudu_util)

#######################################
# mini_oidc
#######################################
# The mini_oidc is used only for tests.
if (KUDU_CLI_TEST_TOOL_ENABLED)
  add_library(mini_oidc mini_oidc.cc)
  target_link_libraries(mini_oidc
    server_process
    gutil
    kudu_test_util
    kudu_util
    jwt_test_certs)
endif()

#######################################
# jwt_test_certs
#######################################
# The jwt_test_certs is used only for tests.
if (KUDU_CLI_TEST_TOOL_ENABLED)
  add_library(jwt_test_certs jwt_test_certs.cc)
  target_link_libraries(jwt_test_certs
    kudu_jwt_util)
endif()

# See the comment in sanitizer_options.cc for details on this library's usage.
# The top-level CMakeLists sets a ${SANITIZER_OPTIONS_OVERRIDE} variable which
# should be linked first into all Kudu binaries.

#######################################
# sanitizer_options
#######################################
if ("${KUDU_USE_ASAN}" OR "${KUDU_USE_TSAN}" OR "${KUDU_USE_UBSAN}")
  add_library(sanitizer_options STATIC sanitizer_options.cc)
  target_link_libraries(sanitizer_options gutil)
  # By default the sanitizers use addr2line utility to symbolize reports.
  # llvm-symbolizer is faster, consumes less memory and produces much better reports.
  # We set KUDU_EXTERNAL_SYMBOLIZER_PATH which is used in sanitizer_options.cc
  # to set the default external_symbolizer_path.
  SET(KUDU_LLVM_SYMBOLIZER_PATH ${THIRDPARTY_INSTALL_UNINSTRUMENTED_DIR}/bin/llvm-symbolizer)
  if (EXISTS ${KUDU_LLVM_SYMBOLIZER_PATH})
    target_compile_definitions(sanitizer_options PRIVATE KUDU_EXTERNAL_SYMBOLIZER_PATH=${KUDU_LLVM_SYMBOLIZER_PATH})
  else()
    message(SEND_ERROR
      "Could not find llvm-symbolizer required for sanitizer builds at ${KUDU_LLVM_SYMBOLIZER_PATH}")
  endif()
endif()

#######################################
# protoc-gen-insertions
#######################################

add_executable(protoc-gen-insertions protoc-gen-insertions.cc)
# Impala needs some extra dependency libs compared to Kudu.
# Note that the order is important.
target_link_libraries(protoc-gen-insertions gutil glog gflags protoc protobuf  ${KUDU_BASE_LIBS})

#######################################
# kudu_test_util
#######################################
# The kudu_test_util is used only for tests.
# Note: Impala needs this.
#if (KUDU_CLI_TEST_TOOL_ENABLED)
  add_library(kudu_test_util
    test_util.cc)
  target_link_libraries(kudu_test_util
    gflags
    glog
    # Impala doesn't have gmock in its toolchain
    #gmock
    gtest
    kudu_util)
#endif()

#######################################
# kudu_test_main
#######################################
if(NOT NO_TESTS)
  add_library(kudu_test_main
    test_main.cc)
  target_link_libraries(kudu_test_main
    ${KRB5_REALM_OVERRIDE}
    gflags
    glog
    gmock
    gtest
    kudu_util
    kudu_test_util)

  if(NOT APPLE)
    target_link_libraries(kudu_test_main
      dl
      rt)
  endif()
endif()

#######################################
# Unit tests
#######################################

SET_KUDU_TEST_LINK_LIBS(kudu_util gutil)
ADD_KUDU_TEST(async_util-test)
ADD_KUDU_TEST(atomic-test)
ADD_KUDU_TEST(bit-util-test)
ADD_KUDU_TEST(bitmap-test)
ADD_KUDU_TEST(bitset-test)
ADD_KUDU_TEST(blocking_queue-test)
ADD_KUDU_TEST(block_bloom_filter-test)
ADD_KUDU_TEST(bloom_filter-test)
ADD_KUDU_TEST(cache-bench RUN_SERIAL true)
ADD_KUDU_TEST(cache-test)
ADD_KUDU_TEST(char_util-test
  DATA_FILES testdata/char_truncate_utf8.txt testdata/char_truncate_ascii.txt)
ADD_KUDU_TEST(countdown_latch-test)
ADD_KUDU_TEST(crc-test RUN_SERIAL true) # has a benchmark
ADD_KUDU_TEST(debug-util-test)
ADD_KUDU_TEST(decimal_util-test)
ADD_KUDU_TEST(easy_json-test)
ADD_KUDU_TEST(env-test LABELS no_tsan)
ADD_KUDU_TEST(env_util-test)
ADD_KUDU_TEST(errno-test)

# There's a move in faststring-test.cc that looks like this:
#
#   f1 = std::move(f1);
#
# Self-moves are generally undesirable, and Clang warns about them via the
# -Wself-move flag. In this particular case, we're explicitly testing self-move
# behavior, so we don't want any warnings.
#
# Unfortunately, if we disable -Wself-move via clang diagnostic pragmas, we'll
# wind up triggering gcc's -Wunknown-pragmas warning. And due to a long-standing
# bug[1], we can't disable -Wunknown-pragmas via GCC diagnostic pragmas. So we
# must disable the warning for the entirety of the compilation unit.
#
# 1. https://gcc.gnu.org/bugzilla/show_bug.cgi?id=53431
if("${COMPILER_FAMILY}" STREQUAL "clang")
  set_source_files_properties(faststring-test.cc PROPERTIES COMPILE_FLAGS
    "-Wno-self-move")
endif()
ADD_KUDU_TEST(faststring-test)

ADD_KUDU_TEST(file_cache-test)
ADD_KUDU_TEST(file_cache-stress-test RUN_SERIAL true)
ADD_KUDU_TEST(flag_tags-test)
ADD_KUDU_TEST(flag_validators-test)
ADD_KUDU_TEST(flags-test)
ADD_KUDU_TEST(group_varint-test)
ADD_KUDU_TEST(hash_util-test)
ADD_KUDU_TEST(hdr_histogram-test)
ADD_KUDU_TEST(int128-test)
ADD_KUDU_TEST(inline_slice-test)
ADD_KUDU_TEST(interval_tree-test)
ADD_KUDU_TEST(jsonreader-test)
ADD_KUDU_TEST(knapsack_solver-test)
ADD_KUDU_TEST(logging-test)
ADD_KUDU_TEST(maintenance_manager-test)
ADD_KUDU_TEST(map-util-test)
ADD_KUDU_TEST(mem_tracker-test)
ADD_KUDU_TEST(memcmpable_varint-test LABELS no_tsan)
ADD_KUDU_TEST(memory/arena-test)
ADD_KUDU_TEST(metrics-test)
ADD_KUDU_TEST(monotime-test)
ADD_KUDU_TEST(mt-hdr_histogram-test RUN_SERIAL true)
ADD_KUDU_TEST(mt-metrics-test RUN_SERIAL true)
ADD_KUDU_TEST(mt-threadlocal-test RUN_SERIAL true)
ADD_KUDU_TEST(net/dns_resolver-test)
ADD_KUDU_TEST(net/net_util-test)
ADD_KUDU_TEST(net/socket-test)
ADD_KUDU_TEST(object_pool-test)
ADD_KUDU_TEST(oid_generator-test)
ADD_KUDU_TEST(once-test)
ADD_KUDU_TEST(os-util-test)
ADD_KUDU_TEST(path_util-test)
ADD_KUDU_TEST(process_memory-test RUN_SERIAL true)
ADD_KUDU_TEST(pstack_watcher-test)
ADD_KUDU_TEST(random-test)
ADD_KUDU_TEST(random_util-test)
ADD_KUDU_TEST(rle-test)
ADD_KUDU_TEST(rolling_log-test)
ADD_KUDU_TEST(rw_mutex-test RUN_SERIAL true)
ADD_KUDU_TEST(rw_semaphore-test)
ADD_KUDU_TEST(rwc_lock-test RUN_SERIAL true)
ADD_KUDU_TEST(safe_math-test)
ADD_KUDU_TEST(scoped_cleanup-test)
ADD_KUDU_TEST(slice-test)
ADD_KUDU_TEST(sorted_disjoint_interval_list-test)
ADD_KUDU_TEST(spinlock_profiling-test)
ADD_KUDU_TEST(stack_watchdog-test PROCESSORS 2)
ADD_KUDU_TEST(status-test)
ADD_KUDU_TEST(string_case-test)
ADD_KUDU_TEST(striped64-test RUN_SERIAL true)
ADD_KUDU_TEST(subprocess-test)
ADD_KUDU_TEST(thread-test)
ADD_KUDU_TEST(threadpool-test)
ADD_KUDU_TEST(throttler-test)
ADD_KUDU_TEST(trace-test PROCESSORS 4)
ADD_KUDU_TEST(ttl_cache-test)
ADD_KUDU_TEST(url-coding-test)
ADD_KUDU_TEST(user-test)
ADD_KUDU_TEST(version_util-test)
ADD_KUDU_TEST(yamlreader-test)

if (NOT APPLE)
  ADD_KUDU_TEST(minidump-test)
endif()

#######################################
# jsonwriter_test_proto
#######################################
if(NOT NO_TESTS)
  PROTOBUF_GENERATE_CPP(
    JSONWRITER_TEST_PROTO_SRCS JSONWRITER_TEST_PROTO_HDRS JSONWRITER_TEST_PROTO_TGTS
    SOURCE_ROOT ${CMAKE_CURRENT_SOURCE_DIR}/../..
    BINARY_ROOT ${CMAKE_CURRENT_BINARY_DIR}/../..
    PROTO_FILES jsonwriter_test.proto)
  add_library(jsonwriter_test_proto ${JSONWRITER_TEST_PROTO_SRCS} ${JSONWRITER_TEST_PROTO_HDRS})
  target_link_libraries(jsonwriter_test_proto
    pb_util_proto
    protobuf)
endif()

#######################################
# jsonwriter-test
#######################################

ADD_KUDU_TEST(jsonwriter-test)
if(NOT NO_TESTS)
  target_link_libraries(jsonwriter-test
    jsonwriter_test_proto)
endif()

#######################################
# pb_util_test_proto
#######################################
if(NOT NO_TESTS)
  PROTOBUF_GENERATE_CPP(
    PROTO_CONTAINER_TEST_PROTO_SRCS PROTO_CONTAINER_TEST_PROTO_HDRS PROTO_CONTAINER_TEST_PROTO_TGTS
    SOURCE_ROOT ${CMAKE_CURRENT_SOURCE_DIR}/../..
    BINARY_ROOT ${CMAKE_CURRENT_BINARY_DIR}/../..
    PROTO_FILES
      proto_container_test.proto
      proto_container_test2.proto
      proto_container_test3.proto
      pb_util_test.proto)
  add_library(pb_util_test_proto
    ${PROTO_CONTAINER_TEST_PROTO_SRCS}
    ${PROTO_CONTAINER_TEST_PROTO_HDRS})
  target_link_libraries(pb_util_test_proto
    pb_util_proto
    protobuf)
endif()

#######################################
# pb_util-test
#######################################

ADD_KUDU_TEST(pb_util-test)
if(NOT NO_TESTS)
  target_link_libraries(pb_util-test
    pb_util_test_proto)
endif()

#######################################
# util/compression tests
#######################################
ADD_KUDU_TEST(compression/compression-test)
if(NOT NO_TESTS)
  target_link_libraries(compression-test
    cfile
    kudu_util_compression)
endif()

#######################################
# curl_util-test
#######################################
ADD_KUDU_TEST(curl_util-test)
if(NOT NO_TESTS)
  target_link_libraries(curl_util-test
    kudu_curl_util)
endif()

#######################################
# jwt-util-test
#######################################
ADD_KUDU_TEST(jwt-util-test)
if(NOT NO_TESTS)
  target_link_libraries(jwt-util-test
    mini_oidc
    server_process
    jwt_test_certs)
endif()

#######################################
# instance_detector-test
#######################################
# Impala doesn't need it.
#ADD_KUDU_TEST(cloud/instance_detector-test)
#if(NOT NO_TESTS)
#  target_link_libraries(instance_detector-test
#    kudu_cloud_util)
#endif()
