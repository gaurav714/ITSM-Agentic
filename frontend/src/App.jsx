import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import Header from "./components/Header.jsx";
import Sidebar from "./components/Sidebar.jsx";
import HelpdeskHomePage from "./pages/HelpdeskHomePage.jsx";
import ConversationPage from "./pages/ConversationPage.jsx";
import TicketHistoryPage from "./pages/TicketHistoryPage.jsx";
import SettingsPage from "./pages/SettingsPage.jsx";

export default function App() {
  const location = useLocation();
  const isHome = location.pathname === "/";
  const isChat = location.pathname.startsWith("/chat");

  return (
    <div className="flex h-screen flex-col">
      {!isHome && <Header />}
      <div className="flex flex-1 overflow-hidden">
        {!isHome && !isChat && <Sidebar />}
        <main
          className={`flex-1 overflow-hidden ${
            isHome ? "bg-slate-950" : "bg-white"
          }`}
        >
          <Routes>
            <Route path="/" element={<HelpdeskHomePage />} />
            <Route path="/chat" element={<ConversationPage />} />
            <Route path="/chat/:workflowId" element={<ConversationPage />} />
            <Route path="/tickets" element={<TicketHistoryPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
