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

#include "udf/udf.h"
#include "udf/udf-internal.h" // for CollectionVal

namespace impala {

using impala_udf::FunctionContext;
using impala_udf::BooleanVal;
using impala_udf::TinyIntVal;
using impala_udf::SmallIntVal;
using impala_udf::IntVal;
using impala_udf::BigIntVal;
using impala_udf::FloatVal;
using impala_udf::DoubleVal;
using impala_udf::StringVal;
using impala_udf::CollectionVal;

class CollectionFunctions {
 public:
  static void ArrayContainsPrepare(FunctionContext* ctx,
      FunctionContext::FunctionStateScope scope);
  static void ArrayContainsClose(FunctionContext* ctx,
      FunctionContext::FunctionStateScope scope);

  static BooleanVal ArrayContainsBoolean(
      FunctionContext* ctx, const CollectionVal& arr, const BooleanVal& item);
  static BooleanVal ArrayContainsTinyInt(
      FunctionContext* ctx, const CollectionVal& arr, const TinyIntVal& item);
  static BooleanVal ArrayContainsSmallInt(
      FunctionContext* ctx, const CollectionVal& arr, const SmallIntVal& item);
  static BooleanVal ArrayContainsInt(
      FunctionContext* ctx, const CollectionVal& arr, const IntVal& item);
  static BooleanVal ArrayContainsBigInt(
      FunctionContext* ctx, const CollectionVal& arr, const BigIntVal& item);
  static BooleanVal ArrayContainsFloat(
      FunctionContext* ctx, const CollectionVal& arr, const FloatVal& item);
  static BooleanVal ArrayContainsDouble(
      FunctionContext* ctx, const CollectionVal& arr, const DoubleVal& item);

  static BooleanVal ArrayContainsString(
      FunctionContext* ctx, const CollectionVal& arr, const StringVal& item);
};

}  // namespace impala
