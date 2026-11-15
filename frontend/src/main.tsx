import {StrictMode} from "react";
import {createRoot} from "react-dom/client";
import {Toast} from "@heroui/react";

import App from "./App";
import "./index.css";

const storedTheme = localStorage.getItem("zed.theme");
const dark = storedTheme ? storedTheme === "dark" : true;
document.documentElement.classList.toggle("dark", dark);
document.documentElement.classList.toggle("light", !dark);
document.documentElement.dataset.theme = dark ? "dark" : "light";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
      <App />
      <Toast.Provider />
  </StrictMode>,
);
