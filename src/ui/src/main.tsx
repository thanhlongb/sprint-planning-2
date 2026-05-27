import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import "./index.css";
import JoinPage from "./pages/JoinPage";
import SessionPage from "./pages/SessionPage";
import ChatSessionPage from "./pages/ChatSessionPage";
import SummaryPage from "./pages/SummaryPage";
import HomePage from "./pages/HomePage";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/join/:session_id" element={<JoinPage />} />
        <Route path="/session/:session_id" element={<SessionPage />} />
        <Route path="/chat/:session_id" element={<ChatSessionPage />} />
        <Route path="/sessions/:session_id/summary" element={<SummaryPage />} />
      </Routes>
      <Toaster position="top-right" richColors />
    </BrowserRouter>
  </React.StrictMode>
);
