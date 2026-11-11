import AsyncStorage from '@react-native-async-storage/async-storage';
import { createContext, ReactNode, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { Vibration } from 'react-native';

export type RobotStatus = {
  status: string;
  status_detail: string;
  fire_detected: boolean;
  fire_confidence: number;
  fire_position: 'LEFT' | 'CENTER' | 'RIGHT' | null;
  pump_on: boolean;
  battery: number | null;
  water_level: number | null;
  distance_m: number | null;
  fps: number;
  camera: string | null;
  detector?: 'yolo' | 'color' | null;
  infer_ms?: number;
  robot_online: boolean;
  simulated: boolean;
  server_time: string;
};

export type HistoryEvent = {
  id: string;
  type: 'FIRE' | 'PATROL';
  time: string;
  image: string;
  pump_on: boolean;
  duration_s: number | null;
  confidence: number | null;
};

export type Settings = {
  serverUrl: string;
  lowWater: number;
  lowBattery: number;
  vibrateOnFire: boolean;
};

const DEFAULT_SETTINGS: Settings = {
  serverUrl: process.env.EXPO_PUBLIC_SERVER_URL ?? 'http://192.168.1.100:5000',
  lowWater: 20,
  lowBattery: 20,
  vibrateOnFire: true,
};
const STORAGE_KEY = 'fire-robot-settings';
const POLL_MS = 1000;

type Ctx = {
  settings: Settings;
  saveSettings: (s: Partial<Settings>) => Promise<void>;
  status: RobotStatus | null;
  connected: boolean;
  lastError: string | null;
  url: (path: string) => string;
};

const RobotContext = createContext<Ctx | null>(null);

export const normalizeUrl = (u: string) => {
  let s = u.trim().replace(/\/+$/, '');
  if (s && !/^https?:\/\//i.test(s)) s = 'http://' + s;
  return s;
};

export async function fetchJson<T>(url: string, timeoutMs = 3000): Promise<T> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(url, { signal: ctrl.signal, headers: { 'Cache-Control': 'no-cache' } });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return (await r.json()) as T;
  } finally {
    clearTimeout(t);
  }
}

export function RobotProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const [loaded, setLoaded] = useState(false);
  const [status, setStatus] = useState<RobotStatus | null>(null);
  const [connected, setConnected] = useState(false);
  const [lastError, setLastError] = useState<string | null>(null);
  const prevFire = useRef(false);

  useEffect(() => {
    AsyncStorage.getItem(STORAGE_KEY)
      .then((raw) => raw && setSettings({ ...DEFAULT_SETTINGS, ...JSON.parse(raw) }))
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, []);

  const saveSettings = useCallback(async (s: Partial<Settings>) => {
    setSettings((cur) => {
      const next = { ...cur, ...s, serverUrl: normalizeUrl(s.serverUrl ?? cur.serverUrl) };
      AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(next)).catch(() => {});
      return next;
    });
  }, []);

  useEffect(() => {
    if (!loaded) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const s = await fetchJson<RobotStatus>(`${settings.serverUrl}/api/status`);
        if (!alive) return;
        setStatus(s);
        setConnected(true);
        setLastError(null);
        if (s.fire_detected && !prevFire.current && settings.vibrateOnFire) {
          Vibration.vibrate([0, 400, 200, 400]);
        }
        prevFire.current = s.fire_detected;
      } catch (e) {
        if (!alive) return;
        setConnected(false);
        setLastError(e instanceof Error ? e.message : String(e));
      }
      if (alive) timer = setTimeout(tick, POLL_MS);
    };
    tick();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [loaded, settings.serverUrl, settings.vibrateOnFire]);

  const url = useCallback((path: string) => `${settings.serverUrl}${path}`, [settings.serverUrl]);

  return (
    <RobotContext.Provider value={{ settings, saveSettings, status, connected, lastError, url }}>
      {children}
    </RobotContext.Provider>
  );
}

export function useRobot() {
  const c = useContext(RobotContext);
  if (!c) throw new Error('useRobot must be used inside RobotProvider');
  return c;
}
