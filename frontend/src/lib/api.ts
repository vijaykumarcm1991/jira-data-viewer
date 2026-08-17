import axios from "axios";

export const api = axios.create({
  baseURL: "/api",
  withCredentials: true,
  headers: { "Content-Type": "application/json" },
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      // Don't redirect for public endpoints; only the auth layer cares.
      const url: string = err.config?.url || "";
      const isPublicEndpoint =
        url.startsWith("/auth/login") ||
        url.startsWith("/auth/me") === false && !url.startsWith("/admin/");
      if (url.startsWith("/admin/")) {
        window.location.href = "/admin/login";
      }
    }
    return Promise.reject(err);
  }
);
