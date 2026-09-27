#!/usr/bin/env node
"use strict";

// Execute only the exact, digest-qualified method bodies supplied by the Python
// qualifier.  The process is intentionally short lived and receives no module
// loader or host capability through the compiled functions.

const fs = require("node:fs");

function compile(body, parameters, names, values, asyncFunction = false) {
  const prefix = asyncFunction ? "async " : "";
  const factory = Function(
    ...names,
    `"use strict"; return ${prefix}function(${parameters.join(",")}) {${body}\n};`,
  );
  return factory(...values);
}

function emptyProducts() {
  return {
    consumable: [],
    nonconsumable: [],
    subscription: [],
    purchased_consumable: [],
    purchased_nonconsumable: [],
    purchased_subscription: [],
    purchased_record_consumable: [],
    purchased_record_subscription: [],
  };
}

function settle() {
  return new Promise((resolve) => setImmediate(resolve));
}

function compileHarmony(bodies) {
  const state = { calls: [], logs: [] };
  const Logger = {
    info: (...values) => state.logs.push(["info", ...values]),
    error: (...values) => state.logs.push(["error", ...values]),
  };
  const FinishStatus = { FINISHED: 1 };
  const JWSUtil = { decodeJwsObj: (value) => value };
  let finishOutcome = "resolve";
  const iap = {
    finishPurchase: (context, parameter) => {
      state.calls.push({ context, parameter });
      return finishOutcome === "reject"
        ? Promise.reject({ code: 77, message: "controlled rejection" })
        : Promise.resolve();
    },
  };
  const finish = compile(
    bodies.finishPurchase,
    ["purchaseOrder"],
    ["iap", "Logger", "TAG"],
    [iap, Logger, "PurchaseDataBehaviorSeam"],
  );
  const deal = compile(
    bodies.dealPurchaseData,
    ["purchaseData"],
    ["JWSUtil", "FinishStatus", "Logger", "TAG"],
    [JWSUtil, FinishStatus, Logger, "PurchaseDataBehaviorSeam"],
  );
  const receiver = {
    context: "context-1",
    finishPurchase(value) {
      return finish.call(receiver, value);
    },
  };
  return {
    state,
    receiver,
    deal: (value) => deal.call(receiver, value),
    finish: (value) => finish.call(receiver, value),
    setFinishOutcome: (value) => { finishOutcome = value; },
  };
}

function compileCordova(bodies) {
  const state = { calls: [], alerts: [], logs: [], reloads: 0 };
  let ownedMessage = { itemList: [], inAppPurchaseDataList: [] };
  let consumeOutcome = { returnCode: 9 };
  const PRODUCTS = {
    consumable: { type: 0, products: [] },
    nonconsumable: { type: 1, products: [] },
    subscription: { type: 2, products: [] },
  };
  const controlledConsole = { log: (...values) => state.logs.push(values) };
  const alert = (value) => state.alerts.push(value);
  const iap = {
    obtainOwnedPurchases: async (parameter) => {
      state.calls.push({ operation: "obtainOwnedPurchases", parameter });
      return ownedMessage;
    },
    consumeOwnedPurchase: async (parameter) => {
      state.calls.push({ operation: "consumeOwnedPurchase", parameter });
      if (consumeOutcome instanceof Error) throw consumeOutcome;
      return consumeOutcome;
    },
  };
  const obtain = compile(
    bodies.obtainOwnedPurchasesFromType,
    ["pType"],
    ["PRODUCTS", "console"],
    [PRODUCTS, controlledConsole],
    true,
  );
  const create = compile(
    bodies.createPurchasedProductOnList,
    ["productId", "purchaseData", "productType"],
    [],
    [],
  );
  const consume = compile(
    bodies.consumeOwnedPurchase,
    ["productId", "purchaseData", "productType"],
    ["DEVELOPERCHALLENGE", "alert", "console"],
    ["controlled-challenge", alert, controlledConsole],
    true,
  );
  const receiver = {
    iap,
    products: emptyProducts(),
    getProduct(productId) { return { id: productId, name: `product-${productId}` }; },
    getProductsInformation() { state.reloads += 1; },
    createPurchasedProductOnList(productId, purchaseData, productType) {
      return create.call(receiver, productId, purchaseData, productType);
    },
  };
  return {
    state,
    receiver,
    obtain: (type) => obtain.call(receiver, type),
    create: (id, data, type) => create.call(receiver, id, data, type),
    consume: (id, data, type) => consume.call(receiver, id, data, type),
    setOwnedMessage: (value) => { ownedMessage = value; },
    setConsumeOutcome: (value) => { consumeOutcome = value; },
  };
}

function pendingPurchase(overrides = {}) {
  return JSON.stringify({
    jwsPurchaseOrder: JSON.stringify({
      finishStatus: 0,
      productType: "1",
      purchaseToken: "token-A",
      purchaseOrderId: "order-A",
      ...overrides,
    }),
  });
}

async function runChecks(bodies) {
  const checks = {};

  {
    const runtime = compileHarmony(bodies.harmony);
    runtime.deal("not-json");
    await settle();
    checks["harmony-invalid-data-is-not-finished"] =
      runtime.state.calls.length === 0 && runtime.state.logs.some((row) => row[0] === "error");
  }
  {
    const runtime = compileHarmony(bodies.harmony);
    runtime.deal(JSON.stringify({ jwsPurchaseOrder: JSON.stringify({ finishStatus: 1, productType: "1" }) }));
    await settle();
    checks["harmony-finished-order-is-not-finished-again"] = runtime.state.calls.length === 0;
  }
  {
    const runtime = compileHarmony(bodies.harmony);
    runtime.deal(pendingPurchase());
    await settle();
    const call = runtime.state.calls[0];
    checks["harmony-pending-order-forwards-exact-identity"] =
      runtime.state.calls.length === 1
      && call.context === "context-1"
      && call.parameter.productType === 1
      && call.parameter.purchaseToken === "token-A"
      && call.parameter.purchaseOrderId === "order-A";
  }
  {
    const runtime = compileHarmony(bodies.harmony);
    runtime.deal(pendingPurchase({ productType: "" }));
    await settle();
    checks["harmony-missing-product-type-blocks-finish"] = runtime.state.calls.length === 0;
  }
  {
    const runtime = compileHarmony(bodies.harmony);
    runtime.setFinishOutcome("reject");
    runtime.finish({ productType: "1", purchaseToken: "token-A", purchaseOrderId: "order-A" });
    await settle();
    checks["harmony-finish-rejection-is-observable"] =
      runtime.state.logs.some((row) => row[0] === "error" && String(row.at(-1)).includes("controlled rejection"));
  }

  {
    const runtime = compileCordova(bodies.cordova);
    runtime.setOwnedMessage({ itemList: ["product-A", "product-B"], inAppPurchaseDataList: ["data-A", "data-B"] });
    await runtime.obtain("consumable");
    checks["cordova-owned-items-preserve-indexed-purchase-data"] =
      JSON.stringify(runtime.receiver.products.purchased_consumable)
      === JSON.stringify([
        { id: "product-A", name: "product-product-A", purchaseData: "data-A" },
        { id: "product-B", name: "product-product-B", purchaseData: "data-B" },
      ]);
  }
  {
    const runtime = compileCordova(bodies.cordova);
    runtime.setConsumeOutcome({ returnCode: 9 });
    await runtime.consume("product-A", "data-A", "consumable");
    const call = runtime.state.calls.find((row) => row.operation === "consumeOwnedPurchase");
    checks["cordova-consume-forwards-exact-purchase-data"] =
      call && call.parameter.inAppPurchaseData === "data-A"
      && call.parameter.developerChallenge === "controlled-challenge";
  }
  {
    const runtime = compileCordova(bodies.cordova);
    runtime.receiver.products.purchased_consumable.push({ id: "sentinel" });
    runtime.setConsumeOutcome({ returnCode: 0 });
    await runtime.consume("product-A", "data-A", "consumable");
    checks["cordova-success-resets-and-reloads"] =
      runtime.receiver.products.purchased_consumable.length === 0 && runtime.state.reloads === 1;
  }
  {
    const runtime = compileCordova(bodies.cordova);
    runtime.receiver.products.purchased_consumable.push({ id: "sentinel" });
    runtime.setConsumeOutcome({ returnCode: 9 });
    await runtime.consume("product-A", "data-A", "consumable");
    checks["cordova-business-failure-retains-state-and-alerts"] =
      runtime.receiver.products.purchased_consumable.length === 1
      && runtime.state.reloads === 0
      && runtime.state.alerts.length === 1;
  }
  {
    const runtime = compileCordova(bodies.cordova);
    runtime.receiver.products.purchased_consumable.push({ id: "sentinel" });
    runtime.setConsumeOutcome(new Error("controlled rejection"));
    await runtime.consume("product-A", "data-A", "consumable");
    checks["cordova-rejection-retains-state-and-logs"] =
      runtime.receiver.products.purchased_consumable.length === 1
      && runtime.state.reloads === 0
      && runtime.state.logs.some((row) => row.some((value) => String(value).includes("controlled rejection")));
  }
  return checks;
}

async function main() {
  const input = JSON.parse(fs.readFileSync(0, "utf8"));
  const checks = await runChecks(input.bodies);
  process.stdout.write(`${JSON.stringify({ schema: "agentlab.purchase_data_behavior_seam_result.v1", checks })}\n`);
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
