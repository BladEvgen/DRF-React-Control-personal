export const isDebug = false;

const localHostname = window.location.hostname;
export const apiUrl = isDebug
  ? `http://${localHostname}:8000`
  : "https://control.krmu.edu.kz";
