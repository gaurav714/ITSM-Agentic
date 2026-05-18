import { api } from "./client.js";

export const submitBrowserDiagnostics = async (sessionId, payload) => {
  const { data } = await api.post("/diagnostics/browser", {
    session_id: sessionId,
    ...payload,
  });
  return data;
};

export const executeBackendAction = async (sessionId, payload) => {
  const { data } = await api.post("/diagnostics/action", {
    session_id: sessionId,
    ...payload,
  });
  return data;
};

export const getDiagnostic = async (id) => {
  const { data } = await api.get(`/diagnostics/${id}`);
  return data;
};
