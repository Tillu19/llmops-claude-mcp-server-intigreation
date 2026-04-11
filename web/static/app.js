const postJson = async (url, payload) => {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  const text = await response.text();
  let data;

  try {
    data = JSON.parse(text);
  } catch {
    data = { raw: text };
  }

  if (!response.ok) {
    throw new Error(JSON.stringify(data, null, 2));
  }

  return data;
};

const setResult = (elementId, value) => {
  const element = document.getElementById(elementId);
  element.textContent =
    typeof value === "string" ? value : JSON.stringify(value, null, 2);
};

const formatAiResult = (data) => {
  if (data.answer) {
    return data.answer;
  }

  if (data.message) {
    return data.message;
  }

  return data;
};

document.getElementById("create-order-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(event.currentTarget);
  const payload = Object.fromEntries(formData.entries());

  if (payload.quantity) {
    payload.quantity = Number(payload.quantity);
  }

  try {
    setResult("create-order-result", "Submitting order...");
    const data = await postJson("/placeOrder", payload);
    setResult("create-order-result", data);
  } catch (err) {
    setResult("create-order-result", err.message);
  }
});

document.querySelectorAll("#lookup-form [data-action]").forEach((button) => {
  button.addEventListener("click", async (event) => {
    const form = document.getElementById("lookup-form");
    const formData = new FormData(form);
    const orderId = formData.get("orderId");

    if (!orderId) {
      setResult("lookup-result", "Order ID is required.");
      return;
    }

    const action = event.currentTarget.dataset.action;
    const routeMap = {
      status: "/getOrderStatus",
      details: "/getOrder",
      summary: "/summarizeOrder",
    };

    try {
      setResult("lookup-result", "Loading...");
      const data = await postJson(routeMap[action], { orderId });
      setResult("lookup-result", data);
    } catch (err) {
      setResult("lookup-result", err.message);
    }
  });
});

document.getElementById("ai-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(event.currentTarget);
  const payload = {
    orderId: formData.get("orderId"),
    question: formData.get("question"),
  };

  try {
    setResult("ai-result", "Thinking...");
    const data = await postJson("/customerQuery", payload);
    setResult("ai-result", formatAiResult(data));
  } catch (err) {
    try {
      setResult("ai-result", formatAiResult(JSON.parse(err.message)));
    } catch {
      setResult("ai-result", err.message);
    }
  }
});
