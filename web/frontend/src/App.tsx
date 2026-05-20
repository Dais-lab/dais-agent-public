import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import CaseList from "./pages/CaseList";
import ModelManagement from "./pages/ModelManagement";
import Monitoring from "./pages/Monitoring";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="cases" element={<CaseList />} />
        <Route path="cases/:caseId" element={<CaseList />} />
        <Route path="models" element={<ModelManagement />} />
        <Route path="monitoring" element={<Monitoring />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
