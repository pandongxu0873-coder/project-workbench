import React from "react";
import {BrandingProvider} from "./components/customer/CustomerIdentity.jsx";
import { createRoot } from "react-dom/client";
import { Theme } from "@astryxdesign/core";
import { neutralTheme } from "@astryxdesign/theme-neutral/built";
import "@astryxdesign/core/reset.css";
import "@astryxdesign/core/astryx.css";
import "@astryxdesign/theme-neutral/theme.css";
import "./styles.css";
import App from "./App.jsx";
import "./graphite-theme.css";
import "./workspace-redesign.css";
import "./project-detail-redesign.css";
import "./signal-redesign.css";
import "./styles/tokens.css";
import "./command-theme.css";
import "./agent-workspace.css";
import "./workbench-system.css";
import "./component-finish.css";
import "./dashboard-home.css";
import "./light-dashboard.css";
import "./portfolio-dashboard.css";
import "./material-dashboard.css";
import "./unified-workbench.css";
import "./split-dashboard.css";
import "./business-continuity.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <Theme theme={neutralTheme} mode="dark">
      <BrandingProvider><App /></BrandingProvider>
    </Theme>
  </React.StrictMode>,
);
