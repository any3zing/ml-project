"use strict";

// Токен читается из поля только в момент отправки и живёт в локальной
// переменной функции. Он не сохраняется в хранилище браузера и cookie
// и не попадает в URL. Весь вывод — через textContent.

const MAX_TEXT_LENGTH = 10000;

// Тексты по машинному коду ошибки; сообщения сервера не показываем
const CODE_MESSAGES = {
  auth_missing: "Нет доступа: введите API-токен.",
  auth_invalid: "Нет доступа: токен неверный.",
  auth_blocked: "Слишком много неудачных попыток ввода токена.",
  rate_limited: "Превышен лимит запросов.",
  unsupported_media_type: "Неподдерживаемый формат запроса.",
  invalid_json: "Сервер не смог разобрать запрос.",
  body_too_large: "Слишком большой запрос.",
  text_too_long: "Текст длиннее 10 000 символов.",
  empty_text: "Введите текст.",
  no_known_features: "В тексте нет слов, известных модели.",
  busy: "Сервис занят, попробуйте ещё раз.",
  timeout: "Сервер не успел обработать запрос.",
};

// Запасной вариант, если машинного кода нет или он незнаком
const STATUS_MESSAGES = {
  400: "Некорректный запрос.",
  401: "Нет доступа.",
  413: "Слишком большой ввод.",
  415: "Неподдерживаемый формат.",
  422: "Некорректный ввод.",
  429: "Слишком много запросов.",
  503: "Сервис временно недоступен.",
  504: "Сервер не успел обработать запрос.",
};

const PREDICTIONS = {
  benign: "benign — обычный запрос",
  malicious: "malicious — похоже на prompt injection",
};

const form = document.getElementById("predict-form");
const tokenInput = document.getElementById("token");
const textInput = document.getElementById("text");
const counter = document.getElementById("counter");
const submitButton = document.getElementById("submit");
const forgetButton = document.getElementById("forget-token");
const statusBox = document.getElementById("status");
const resultBox = document.getElementById("result");
const out = {
  prediction: document.getElementById("r-prediction"),
  label: document.getElementById("r-label"),
  version: document.getElementById("r-version"),
  requestId: document.getElementById("r-request-id"),
  json: document.getElementById("r-json"),
};

function updateCounter() {
  // считаем символы (code points), как сервер, а не UTF-16
  const length = Array.from(textInput.value).length;
  counter.textContent = `${length} / ${MAX_TEXT_LENGTH}`;
}

function showStatus(kind, message, requestId) {
  statusBox.className = `status ${kind}`;
  statusBox.textContent = message;
  if (requestId) {
    const line = document.createElement("div");
    line.className = "mono";
    line.textContent = `request_id: ${requestId}`;
    statusBox.append(line);
  }
  statusBox.hidden = false;
}

function showResult(body) {
  const prediction = String(body.prediction);
  out.prediction.textContent = PREDICTIONS[prediction] || prediction;
  out.prediction.dataset.kind = prediction === "malicious" ? "malicious" : "benign";
  out.label.textContent = String(body.label);
  out.version.textContent = String(body.model_version);
  out.requestId.textContent = String(body.request_id);
  out.json.textContent = JSON.stringify(body, null, 2);
  resultBox.hidden = false;
}

function errorMessage(status, body, retryAfter) {
  const raw = body && body.error && body.error.code;
  // показываем только «машинный» код из ожидаемого алфавита
  const code = typeof raw === "string" && /^[a-z0-9_]{1,40}$/.test(raw) ? raw : "";
  let message = CODE_MESSAGES[code] || STATUS_MESSAGES[status] || "Ошибка сервиса.";
  if (status === 429 && /^\d{1,5}$/.test(retryAfter || "")) {
    message += ` Повторите через ${retryAfter} с.`;
  }
  return `${message} (HTTP ${status}${code ? `, ${code}` : ""})`;
}

async function readJson(response) {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

async function onSubmit(event) {
  event.preventDefault();
  const token = tokenInput.value.trim();
  const headers = { "Content-Type": "application/json" };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  resultBox.hidden = true;
  submitButton.disabled = true;
  showStatus("pending", "Отправка…");

  try {
    let response;
    try {
      response = await fetch("/predict", {
        method: "POST",
        headers,
        body: JSON.stringify({ text: textInput.value }),
        cache: "no-store",
        credentials: "omit",
        redirect: "error",
      });
    } catch {
      // сеть недоступна или в токене символы, недопустимые в заголовке
      showStatus("error", "Нет связи с сервером или токен содержит недопустимые символы.");
      return;
    }

    const requestId = response.headers.get("X-Request-ID");
    const body = await readJson(response);
    if (response.ok && body) {
      statusBox.hidden = true;
      showResult(body);
    } else {
      const retryAfter = response.headers.get("Retry-After");
      showStatus("error", errorMessage(response.status, body, retryAfter), requestId);
    }
  } finally {
    submitButton.disabled = false;
  }
}

textInput.addEventListener("input", updateCounter);
forgetButton.addEventListener("click", () => {
  tokenInput.value = "";
  tokenInput.focus();
});
form.addEventListener("submit", onSubmit);
updateCounter();

