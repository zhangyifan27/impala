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

#include "exprs/collection-functions.h"
#include "exprs/scalar-expr.h"
#include "runtime/collection-value.h"
#include "runtime/descriptors.h"
#include "runtime/string-value.h"
#include "runtime/timestamp-value.h"
#include "runtime/date-value.h"
#include "runtime/types.h"
#include "runtime/tuple.h"
#include "udf/udf-internal.h"

#include <cstring>

namespace impala {

using impala_udf::FunctionContext;
using impala_udf::BooleanVal;
using impala_udf::CollectionVal;

namespace {

struct ArrayContainsState {
  const TupleDescriptor* tuple_desc = nullptr;
  const SlotDescriptor* slot_desc = nullptr;
  int tuple_byte_size = 0;
  int slot_offset = 0;
  NullIndicatorOffset null_offset;
};

ScalarExpr* GetArrayExpr(FunctionContext* ctx) {
  const auto& non_constant_args = ctx->impl()->non_constant_args();
  for (const auto& child : non_constant_args) {
    if (child.first != nullptr && child.first->type().IsCollectionType()) {
      return child.first;
    }
  }
  return nullptr;
}

bool InitArrayContainsState(FunctionContext* ctx, ArrayContainsState* state) {
  DCHECK(state != nullptr);
  ScalarExpr* array_expr = GetArrayExpr(ctx);
  if (array_expr == nullptr) {
    ctx->SetError("array_contains requires a non-constant ARRAY argument.");
    return false;
  }
  const TupleDescriptor* tuple_desc = array_expr->GetCollectionTupleDesc();
  if (tuple_desc == nullptr || tuple_desc->slots().empty()) {
    ctx->SetError("Failed to resolve collection item tuple descriptor for array_contains.");
    return false;
  }
  if (tuple_desc->slots().size() != 1) {
    ctx->SetError("array_contains only supports ARRAYs with a single element slot.");
    return false;
  }
  state->tuple_desc = tuple_desc;
  state->slot_desc = tuple_desc->slots()[0];
  state->tuple_byte_size = tuple_desc->byte_size();
  state->slot_offset = state->slot_desc->tuple_offset();
  state->null_offset = state->slot_desc->null_indicator_offset();
  return true;
}

ArrayContainsState* GetOrCreateArrayState(FunctionContext* ctx) {
  ArrayContainsState* state = reinterpret_cast<ArrayContainsState*>(
      ctx->GetFunctionState(FunctionContext::THREAD_LOCAL));
  if (state != nullptr) return state;
  state = new ArrayContainsState();
  if (!InitArrayContainsState(ctx, state)) {
    delete state;
    ctx->SetFunctionState(FunctionContext::THREAD_LOCAL, nullptr);
    return nullptr;
  }
  ctx->SetFunctionState(FunctionContext::THREAD_LOCAL, state);
  return state;
}

inline bool IsElementNull(const ArrayContainsState* state, Tuple* tuple) {
  return state->slot_desc->is_nullable() && tuple->IsNull(state->null_offset);
}

template <typename NativeType, typename ValType>
BooleanVal ArrayContainsPrimitive(FunctionContext* ctx, const CollectionVal& arr,
    const ValType& item) {
  if (arr.is_null || item.is_null) return BooleanVal::null();
  ArrayContainsState* state = GetOrCreateArrayState(ctx);
  if (state == nullptr) return BooleanVal::null();
  DCHECK_GT(state->tuple_byte_size, 0);
  uint8_t* tuple_ptr = arr.ptr;
  for (int i = 0; i < arr.num_tuples; ++i, tuple_ptr += state->tuple_byte_size) {
    Tuple* tuple = reinterpret_cast<Tuple*>(tuple_ptr);
    if (IsElementNull(state, tuple)) continue;
    NativeType current_value =
        *reinterpret_cast<NativeType*>(tuple->GetSlot(state->slot_offset));
    if (current_value == item.val) return BooleanVal(true);
  }
  return BooleanVal(false);
}

} // namespace

void CollectionFunctions::ArrayContainsPrepare(FunctionContext* ctx,
    FunctionContext::FunctionStateScope scope) {
  if (scope != FunctionContext::THREAD_LOCAL) return;
  auto* state = new ArrayContainsState();
  if (!InitArrayContainsState(ctx, state)) {
    delete state;
    state = nullptr;
  }
  ctx->SetFunctionState(scope, state);
}

void CollectionFunctions::ArrayContainsClose(FunctionContext* ctx,
    FunctionContext::FunctionStateScope scope) {
  if (scope != FunctionContext::THREAD_LOCAL) return;
  delete reinterpret_cast<ArrayContainsState*>(
      ctx->GetFunctionState(FunctionContext::THREAD_LOCAL));
  ctx->SetFunctionState(FunctionContext::THREAD_LOCAL, nullptr);
}

BooleanVal CollectionFunctions::ArrayContainsBoolean(
    FunctionContext* ctx, const CollectionVal& arr, const BooleanVal& item) {
  return ArrayContainsPrimitive<bool>(ctx, arr, item);
}

BooleanVal CollectionFunctions::ArrayContainsTinyInt(
    FunctionContext* ctx, const CollectionVal& arr, const TinyIntVal& item) {
  return ArrayContainsPrimitive<int8_t>(ctx, arr, item);
}

BooleanVal CollectionFunctions::ArrayContainsSmallInt(
    FunctionContext* ctx, const CollectionVal& arr, const SmallIntVal& item) {
  return ArrayContainsPrimitive<int16_t>(ctx, arr, item);
}

BooleanVal CollectionFunctions::ArrayContainsInt(
    FunctionContext* ctx, const CollectionVal& arr, const IntVal& item) {
  return ArrayContainsPrimitive<int32_t>(ctx, arr, item);
}

BooleanVal CollectionFunctions::ArrayContainsBigInt(
    FunctionContext* ctx, const CollectionVal& arr, const BigIntVal& item) {
  return ArrayContainsPrimitive<int64_t>(ctx, arr, item);
}

BooleanVal CollectionFunctions::ArrayContainsFloat(
    FunctionContext* ctx, const CollectionVal& arr, const FloatVal& item) {
  return ArrayContainsPrimitive<float>(ctx, arr, item);
}

BooleanVal CollectionFunctions::ArrayContainsDouble(
    FunctionContext* ctx, const CollectionVal& arr, const DoubleVal& item) {
  return ArrayContainsPrimitive<double>(ctx, arr, item);
}

BooleanVal CollectionFunctions::ArrayContainsString(
    FunctionContext* ctx, const CollectionVal& arr, const StringVal& item) {
  if (arr.is_null || item.is_null) return BooleanVal::null();
  ArrayContainsState* state = GetOrCreateArrayState(ctx);
  if (state == nullptr) return BooleanVal::null();
  DCHECK_GT(state->tuple_byte_size, 0);
  uint8_t* tuple_ptr = arr.ptr;
  for (int i = 0; i < arr.num_tuples; ++i, tuple_ptr += state->tuple_byte_size) {
    Tuple* tuple = reinterpret_cast<Tuple*>(tuple_ptr);
    if (IsElementNull(state, tuple)) continue;
    StringValue* current_value =
        reinterpret_cast<StringValue*>(tuple->GetSlot(state->slot_offset));
    if (current_value->IrLen() != item.len) continue;
    if (current_value->IrLen() == 0) return BooleanVal(true);
    if (current_value->IrPtr() != nullptr && item.ptr != nullptr &&
        memcmp(current_value->IrPtr(), reinterpret_cast<const char*>(item.ptr),
            current_value->IrLen()) == 0) {
      return BooleanVal(true);
    }
  }
  return BooleanVal(false);
}

BooleanVal CollectionFunctions::ArrayContainsTimestamp(
    FunctionContext* ctx, const CollectionVal& arr, const TimestampVal& item) {
  if (arr.is_null || item.is_null) return BooleanVal::null();
  ArrayContainsState* state = GetOrCreateArrayState(ctx);
  if (state == nullptr) return BooleanVal::null();
  DCHECK_GT(state->tuple_byte_size, 0);
  
  uint8_t* tuple_ptr = arr.ptr;
  for (int i = 0; i < arr.num_tuples; ++i, tuple_ptr += state->tuple_byte_size) {
    Tuple* tuple = reinterpret_cast<Tuple*>(tuple_ptr);
    if (IsElementNull(state, tuple)) continue;
    
    TimestampValue* current_value =
        reinterpret_cast<TimestampValue*>(tuple->GetSlot(state->slot_offset));
    TimestampVal current_val = current_value->ToTimestampVal();

    // Compare both date and time_of_day fields
    if (current_val.date == item.date && 
        current_val.time_of_day == item.time_of_day) {
      return BooleanVal(true);
    }
  }
  return BooleanVal(false);
}

BooleanVal CollectionFunctions::ArrayContainsDecimal(
    FunctionContext* ctx, const CollectionVal& arr, const DecimalVal& item) {
  if (arr.is_null || item.is_null) return BooleanVal::null();
  ArrayContainsState* state = GetOrCreateArrayState(ctx);
  if (state == nullptr) return BooleanVal::null();
  DCHECK_GT(state->tuple_byte_size, 0);

  const ColumnType& type = ColumnType::FromThrift(state->slot_desc->type());
  int byte_size = type.GetByteSize();

  uint8_t* tuple_ptr = arr.ptr;
  for (int i = 0; i < arr.num_tuples; ++i, tuple_ptr += state->tuple_byte_size) {
    Tuple* tuple = reinterpret_cast<Tuple*>(tuple_ptr);
    if (IsElementNull(state, tuple)) continue;

    void* slot_ptr = tuple->GetSlot(state->slot_offset);
    bool equal = false;
    switch (byte_size) {
      case 4:
        equal = (*reinterpret_cast<int32_t*>(slot_ptr) == item.val4);
        break;
      case 8:
        equal = (*reinterpret_cast<int64_t*>(slot_ptr) == item.val8);
        break;
      case 16:
        equal = (*reinterpret_cast<__int128_t*>(slot_ptr) == item.val16);
        break;
      default:
        DCHECK(false) << "Invalid decimal byte size: " << byte_size;
        return BooleanVal::null();
    }

    if (equal) return BooleanVal(true);
  }
  return BooleanVal(false);
}

BooleanVal CollectionFunctions::ArrayContainsDate(
    FunctionContext* ctx, const CollectionVal& arr, const DateVal& item) {
  return ArrayContainsPrimitive<int32_t>(ctx, arr, item);
}

}  // namespace impala
