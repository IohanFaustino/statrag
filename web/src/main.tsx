import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles/tokens.css";
import "./styles/app.css";
import "./styles/neon.css";
import "./styles/tutor.css";
import "./styles/chapter.css";
import "./styles/broadsheet.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
