import { api } from "./client.js";

export const listTickets = async () => {
  const { data } = await api.get("/tickets");
  return data;
};

export const createTicket = async (sessionId, draft) => {
  const { data } = await api.post("/tickets/create", {
    session_id: sessionId,
    draft,
  });
  return data;
};
