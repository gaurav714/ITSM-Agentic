import axios from "axios";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
export const API_LOCAL_FALLBACK_URL = "http://localhost:8000";

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { "Content-Type": "application/json" },
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const canRetryAgainstLocalhost =
      !error?.response &&
      !error?.config?.__retriedLocalhost &&
      normalizeBaseUrl(API_BASE_URL) !== normalizeBaseUrl(API_LOCAL_FALLBACK_URL);

    if (!canRetryAgainstLocalhost) {
      return Promise.reject(error);
    }

    return api.request({
      ...error.config,
      baseURL: API_LOCAL_FALLBACK_URL,
      __retriedLocalhost: true,
    });
  },
);

function normalizeBaseUrl(value) {
  return String(value || "").replace(/\/+$/, "").toLowerCase();
}
