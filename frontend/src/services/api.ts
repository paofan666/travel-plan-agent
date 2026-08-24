import axios from "axios";

import type {
  Itinerary,
  TripDetailResponse,
  TripEditPayload,
  TripListResponse,
  TripRequestPayload,
  TripSaveResponse,
  WeatherForecastResponse,
} from "../types";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000,
});

// 行程生成会串行执行检索改写、重排、Planner 和地图补全，耗时可能
// 超过普通接口。若沿用 120 秒超时，浏览器会先放弃请求，而后端仍会
// 继续生成，最终造成“后端已完成但前端没有展示”的假象。
const TRIP_GENERATION_TIMEOUT_MS = 360000;

export async function generateTrip(payload: TripRequestPayload): Promise<Itinerary> {
  const response = await api.post<Itinerary>("/trip/generate", payload, {
    timeout: TRIP_GENERATION_TIMEOUT_MS,
  });
  return response.data;
}

export async function editTrip(payload: TripEditPayload): Promise<Itinerary> {
  const response = await api.post<Itinerary>("/trip/edit", payload);
  return response.data;
}

export async function saveTrip(itinerary: Itinerary): Promise<TripSaveResponse> {
  const response = await api.post<TripSaveResponse>("/trip/save", {
    trip_id: itinerary.trip_id,
    itinerary,
    user_id: "frontend_demo_user",
  });
  return response.data;
}

export async function listTrips(): Promise<TripListResponse> {
  const response = await api.get<TripListResponse>("/trip");
  return response.data;
}

export async function getTripDetail(tripId: string): Promise<TripDetailResponse> {
  const response = await api.get<TripDetailResponse>(`/trip/${tripId}`);
  return response.data;
}

export async function deleteTrip(tripId: string): Promise<void> {
  await api.delete(`/trip/${tripId}`);
}

export async function fetchWeatherForecast(city: string): Promise<WeatherForecastResponse> {
  const response = await api.get<WeatherForecastResponse>("/weather/forecast", {
    params: { city },
  });
  return response.data;
}

export function getMarkdownExportUrl(tripId: string): string {
  return `${API_BASE_URL}/export/${encodeURIComponent(tripId)}/markdown`;
}

export function getPdfExportUrl(tripId: string): string {
  return `${API_BASE_URL}/export/${encodeURIComponent(tripId)}/pdf`;
}

export default api;
