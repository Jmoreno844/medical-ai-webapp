import axios from "axios";

const API_URL = process.env.NEXT_PUBLIC_API_URL;

const axiosInstance = axios.create({
  baseURL: API_URL,
  withCredentials: true, // Move withCredentials here
  headers: {
    "Content-Type": "application/json",
  },
});

export default axiosInstance;
