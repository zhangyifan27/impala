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

# See the comment in krb5_realm_override.cc for details on this library's usage.
# The top-level CMakeLists sets a ${KRB5_REALM_OVERRIDE} variable which should
# be linked first into all Kudu binaries.

# Target including all protobuf-generated code.
add_custom_target(kudu-security-proto-deps)

##############################
# krb5_realm_override
##############################

add_library(krb5_realm_override STATIC krb5_realm_override.cc)
target_link_libraries(krb5_realm_override glog)
if(NOT APPLE)
  target_link_libraries(krb5_realm_override dl)
endif()

add_definitions(-DKUDU_HEADERS_USE_SHORT_STATUS_MACROS)

##############################
# token_proto
##############################

PROTOBUF_GENERATE_CPP(
  TOKEN_PROTO_SRCS TOKEN_PROTO_HDRS TOKEN_PROTO_TGTS
  SOURCE_ROOT ${CMAKE_CURRENT_SOURCE_DIR}/../..
  BINARY_ROOT ${CMAKE_CURRENT_BINARY_DIR}/../..
  PROTO_FILES token.proto)
set(TOKEN_PROTO_LIBS protobuf pb_util_proto)
ADD_EXPORTABLE_LIBRARY(token_proto
  SRCS ${TOKEN_PROTO_SRCS}
  DEPS ${TOKEN_PROTO_LIBS}
  NONLINK_DEPS ${TOKEN_PROTO_TGTS})

add_dependencies(kudu-security-proto-deps ${TOKEN_PROTO_TGTS})

##############################
# security
##############################

# Check for krb5_get_init_creds_opt_set_out_ccache, which is not available in versions
# of MIT Kerberos older than krb5-1.6, and is also not present in Heimdal kerberos.
include(CheckLibraryExists)
check_library_exists("krb5" krb5_get_init_creds_opt_set_out_ccache
  ${KERBEROS_LIBRARY} HAVE_KRB5_GET_INIT_CREDS_OPT_SET_OUT_CCACHE)
if(HAVE_KRB5_GET_INIT_CREDS_OPT_SET_OUT_CCACHE)
  add_definitions(-DHAVE_KRB5_GET_INIT_CREDS_OPT_SET_OUT_CCACHE=1)
endif()

# Fall back to using the ported functionality if we're using an older version of OpenSSL.
if (${OPENSSL_VERSION} VERSION_LESS "1.0.2")
  set(PORTED_X509_CHECK_HOST_CC "x509_check_host.cc")
endif()

set(SECURITY_SRCS
  ca/cert_management.cc
  cert.cc
  crypto.cc
  kerberos_util.cc
  gssapi.cc
  init.cc
  ${PORTED_X509_CHECK_HOST_CC}
  security_flags.cc
  simple_acl.cc
  tls_context.cc
  tls_handshake.cc
  tls_socket.cc
  token_verifier.cc
  token_signer.cc
  token_signing_key.cc
  )

set(SECURITY_LIBS
  gutil
  kudu_util
  token_proto

  gssapi_krb5
  krb5
  openssl_crypto
  openssl_ssl)

ADD_EXPORTABLE_LIBRARY(security
  SRCS ${SECURITY_SRCS}
  DEPS ${SECURITY_LIBS})

# Since Kudu tests are explicitly disabled, we want to expose some of their sources
# to Impala using another variable.
set(SECURITY_TEST_SRCS_FOR_IMPALA test/mini_kdc.cc)
add_library(security-test-for-impala ${SECURITY_TEST_SRCS_FOR_IMPALA})
target_link_libraries(security-test-for-impala
  gutil
  kudu_test_util
  kudu_util
  security)

##############################
# mini_kdc
##############################

# The mini_kdc is used only for tests.
# Note: Impala needs it.
#if (KUDU_CLI_TEST_TOOL_ENABLED)
  set(MINI_KDC_SRCS test/mini_kdc.cc)

  add_library(mini_kdc ${MINI_KDC_SRCS})
  target_link_libraries(mini_kdc
    gutil
    kudu_test_util
    kudu_util)
#endif()

##############################
# security_test_util
##############################

if (NOT NO_TESTS)
  set(SECURITY_TEST_SRCS
    security-test-util.cc
    test/test_certs.cc
    test/test_pass.cc)

  add_library(security_test_util ${SECURITY_TEST_SRCS})
  target_link_libraries(security_test_util
    gutil
    kudu_test_util
    kudu_util
    security)
endif()

#########################################
# Unit tests
#########################################

SET_KUDU_TEST_LINK_LIBS(
  mini_kdc
  security
  security_test_util)

ADD_KUDU_TEST(ca/cert_management-test)
ADD_KUDU_TEST(cert-test)
ADD_KUDU_TEST(crypto-test)
ADD_KUDU_TEST(test/mini_kdc-test)
ADD_KUDU_TEST(tls_handshake-test)
ADD_KUDU_TEST(tls_socket-test PROCESSORS 2)
ADD_KUDU_TEST(token-test)
