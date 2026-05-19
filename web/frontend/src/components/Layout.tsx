import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";
import Header from "./Header";

export default function Layout() {
  return (
    <div className="flex h-screen overflow-hidden bg-surface">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-auto bg-surface">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
