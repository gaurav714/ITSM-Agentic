import { create } from "zustand";

const generateSessionId = () => {
  if (typeof crypto !== "undefined" && crypto.randomUUID)
    return crypto.randomUUID();
  return (
    "sess-" + Math.random().toString(36).slice(2) + Date.now().toString(36)
  );
};

export const useConversationStore = create((set, get) => ({
  sessionId: generateSessionId(),
  messages: [],
  cards: [],
  workflow: null,
  state: "idle",
  loading: false,

  reset: () =>
    set({
      sessionId: generateSessionId(),
      messages: [],
      cards: [],
      workflow: null,
      state: "idle",
      loading: false,
    }),

  setLoading: (loading) => set({ loading }),

  addUserMessage: (text) =>
    set((s) => ({
      messages: [...s.messages, { role: "user", text, ts: Date.now() }],
    })),

  addAssistantResponse: (response) =>
    set((s) => ({
      messages: [
        ...s.messages,
        { role: "assistant", text: response.message, ts: Date.now() },
      ],
      cards: response.cards?.length
        ? [...s.cards, ...response.cards.map((c) => ({ ...c, ts: Date.now() }))]
        : s.cards,
      workflow: response.workflow ?? s.workflow,
      state: response.state ?? s.state,
    })),

  appendCard: (card) =>
    set((s) => ({ cards: [...s.cards, { ...card, ts: Date.now() }] })),
}));
