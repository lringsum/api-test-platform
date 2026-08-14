import axios from 'axios'

export const http = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1', timeout: 10_000, withCredentials: true })

http.interceptors.response.use(
  (response) => response.data,
  (error) => Promise.reject(error),
)
