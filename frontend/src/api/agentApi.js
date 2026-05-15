import { api } from "./client.js";

export const sendAgentMessage = async (sessionId, message) => {
  const { data } = await api.post("/agent/message", {
    session_id: sessionId,
    message,
  });
  return data;
};

export const startWorkflow = async (sessionId, workflowId) => {
  const { data } = await api.post("/agent/start_workflow", {
    session_id: sessionId,
    workflow_id: workflowId,
  });
  return data;
};

export const listWorkflows = async () => {
  const { data } = await api.get("/workflows");
  return data;
};
