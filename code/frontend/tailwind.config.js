/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bgpx: {
          ink: '#E5F0FF',
          muted: '#94A3B8',
          subtle: '#64748B',
          black: '#020617',
          navy: '#07111F',
          navy2: '#0B1628',
          panel: '#0F1B2E',
          panel2: '#111F35',
          line: '#21314A',
          line2: '#2B3D5B',
          cyan: '#38BDF8',
          cyan2: '#0EA5E9',
          cyan3: '#67E8F9',
          violet: '#6366F1',
          violet2: '#8B5CF6',
          green: '#22C55E',
          amber: '#F59E0B',
          red: '#EF4444',
        },
      },
      borderRadius: {
        'bgpx-card': '1.25rem',
        'bgpx-panel': '1.5rem',
      },
      boxShadow: {
        glow: '0 0 60px rgba(56, 189, 248, 0.18)',
        'glow-violet': '0 0 60px rgba(99, 102, 241, 0.16)',
      },
      fontFamily: {
        sans: [
          'Inter',
          'ui-sans-serif',
          'system-ui',
          '-apple-system',
          'BlinkMacSystemFont',
          'Segoe UI',
          'sans-serif',
        ],
        mono: ['SFMono-Regular', 'Consolas', 'Liberation Mono', 'Menlo', 'monospace'],
      },
    },
  },
  plugins: [],
}
