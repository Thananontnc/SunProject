export const colors = {
  bg: '#0B1018',
  card: '#151C27',
  cardBorder: '#212B3A',
  text: '#F2F5FA',
  sub: '#8B97AA',
  green: '#3DDC84',
  red: '#FF4D4F',
  orange: '#FF9F2E',
  blue: '#3B9BFF',
  yellow: '#FFD23F',
  muted: '#3A4556',
};

export const statusColor = (status: string): string => {
  switch (status) {
    case 'Extinguishing':
      return colors.blue;
    case 'Approaching':
    case 'Moving Forward':
      return colors.orange;
    case 'Target Reached':
      return colors.yellow;
    case 'Completed':
    case 'Patrolling':
      return colors.green;
    default:
      return colors.sub;
  }
};

export const levelColor = (pct: number, low: number) =>
  pct <= low ? colors.red : pct <= low * 2 ? colors.orange : colors.green;
