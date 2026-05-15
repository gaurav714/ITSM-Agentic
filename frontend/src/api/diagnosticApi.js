import { api } from "./client.js";

export const submitBrowserDiagnostics = async (sessionId, payload) => {
  const { data } = await api.post("/diagnostics/browser", {
    session_id: sessionId,
    ...payload,
  });
  return data;
};

export const submitLocalActionResult = async (sessionId, payload) => {
  const { data } = await api.post("/diagnostics/local-action", {
    session_id: sessionId,
    ...payload,
    raw: payload,
  });
  return data;
};

export const getDiagnostic = async (id) => {
  const { data } = await api.get(`/diagnostics/${id}`);
  return data;
};
