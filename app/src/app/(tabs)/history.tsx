import Ionicons from '@expo/vector-icons/Ionicons';
import { useFocusEffect } from 'expo-router';
import { useCallback, useMemo, useState } from 'react';
import { Image, Modal, Pressable, RefreshControl, SectionList, StyleSheet, Text, View } from 'react-native';

import { colors } from '@/lib/theme';
import { fetchJson, HistoryEvent, useRobot } from '@/lib/robot';

type Filter = 'ALL' | 'FIRE' | 'PATROL';

const dayLabel = (iso: string) =>
  new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' });
const timeLabel = (iso: string) =>
  new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });

const durationLabel = (d: number | null) => (d == null ? 'ongoing' : d < 0 ? 'unknown' : `${d} s`);

export default function HistoryScreen() {
  const { url } = useRobot();
  const [items, setItems] = useState<HistoryEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>('ALL');
  const [open, setOpen] = useState<HistoryEvent | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await fetchJson<HistoryEvent[]>(url('/api/history'), 5000));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [url]);

  useFocusEffect(
    useCallback(() => {
      load();
      const t = setInterval(load, 5000);
      return () => clearInterval(t);
    }, [load]),
  );

  const sections = useMemo(() => {
    const map = new Map<string, HistoryEvent[]>();
    for (const e of items) {
      if (filter !== 'ALL' && e.type !== filter) continue;
      const k = dayLabel(e.time);
      if (!map.has(k)) map.set(k, []);
      map.get(k)!.push(e);
    }
    return [...map.entries()].map(([title, data]) => ({ title, data }));
  }, [items, filter]);

  return (
    <View style={{ flex: 1 }}>
      <View style={styles.filters}>
        {(['ALL', 'FIRE', 'PATROL'] as Filter[]).map((f) => (
          <Pressable key={f} onPress={() => setFilter(f)} style={[styles.chip, filter === f && styles.chipOn]}>
            <Text style={[styles.chipText, filter === f && { color: colors.bg }]}>
              {f === 'ALL' ? 'All' : f === 'FIRE' ? 'Fire detected' : 'Patrol'}
            </Text>
          </Pressable>
        ))}
      </View>
      <SectionList
        sections={sections}
        keyExtractor={(e) => e.id}
        contentContainerStyle={{ padding: 16, paddingTop: 4 }}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor={colors.sub} />}
        stickySectionHeadersEnabled={false}
        renderSectionHeader={({ section }) => <Text style={styles.day}>{section.title}</Text>}
        ListEmptyComponent={
          <Text style={styles.empty}>{error ? `Can't load history (${error})` : 'No events yet'}</Text>
        }
        renderItem={({ item }) => (
          <Pressable style={styles.item} onPress={() => setOpen(item)}>
            <Image source={{ uri: url(item.image) }} style={styles.thumb} />
            <View style={{ flex: 1, gap: 4 }}>
              <View style={styles.rowBetween}>
                <Text style={styles.time}>{timeLabel(item.time)}</Text>
                <Tag type={item.type} />
              </View>
              <Text style={styles.meta}>Pump: {item.pump_on ? 'ON' : 'OFF'}</Text>
              {item.type === 'FIRE' && (
                <Text style={styles.meta}>
                  Duration: {durationLabel(item.duration_s)}
                </Text>
              )}
            </View>
            <Ionicons name="chevron-forward" size={18} color={colors.sub} />
          </Pressable>
        )}
      />

      <Modal visible={!!open} transparent animationType="fade" onRequestClose={() => setOpen(null)}>
        <Pressable style={styles.backdrop} onPress={() => setOpen(null)}>
          {open && (
            <View style={styles.detail}>
              <Image source={{ uri: url(open.image) }} style={styles.big} resizeMode="contain" />
              <View style={[styles.rowBetween, { marginTop: 12 }]}>
                <Text style={styles.time}>
                  {dayLabel(open.time)} {timeLabel(open.time)}
                </Text>
                <Tag type={open.type} />
              </View>
              <Text style={styles.meta}>Pump: {open.pump_on ? 'ON' : 'OFF'}</Text>
              {open.type === 'FIRE' && (
                <>
                  <Text style={styles.meta}>
                    Duration: {durationLabel(open.duration_s)}
                  </Text>
                  {open.confidence != null && (
                    <Text style={styles.meta}>Confidence: {Math.round(open.confidence * 100)}%</Text>
                  )}
                </>
              )}
            </View>
          )}
        </Pressable>
      </Modal>
    </View>
  );
}

function Tag({ type }: { type: HistoryEvent['type'] }) {
  const c = type === 'FIRE' ? colors.red : colors.blue;
  return (
    <View style={[styles.tag, { borderColor: c, backgroundColor: c + '22' }]}>
      <Text style={[styles.tagText, { color: c }]}>{type === 'FIRE' ? 'FIRE DETECTED' : 'PATROL'}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  filters: { flexDirection: 'row', gap: 8, paddingHorizontal: 16, paddingVertical: 10 },
  chip: { paddingHorizontal: 14, paddingVertical: 7, borderRadius: 16, backgroundColor: colors.card },
  chipOn: { backgroundColor: colors.green },
  chipText: { color: colors.text, fontSize: 13, fontWeight: '600' },
  day: { color: colors.green, fontWeight: '700', fontSize: 13, marginTop: 12, marginBottom: 8 },
  item: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    backgroundColor: colors.card,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: colors.cardBorder,
    padding: 10,
    marginBottom: 10,
  },
  thumb: { width: 96, height: 72, borderRadius: 8, backgroundColor: '#000' },
  rowBetween: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 },
  time: { color: colors.text, fontWeight: '700', fontSize: 14 },
  meta: { color: colors.sub, fontSize: 12 },
  tag: { borderWidth: 1, borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2 },
  tagText: { fontSize: 10, fontWeight: '800' },
  empty: { color: colors.sub, textAlign: 'center', marginTop: 40 },
  backdrop: { flex: 1, backgroundColor: '#000C', justifyContent: 'center', padding: 16 },
  detail: { backgroundColor: colors.card, borderRadius: 16, padding: 12, gap: 4 },
  big: { width: '100%', aspectRatio: 4 / 3, borderRadius: 10, backgroundColor: '#000' },
});
