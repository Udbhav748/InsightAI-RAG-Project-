/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        display: ['"Plus Jakarta Sans"', 'Inter', 'system-ui', 'sans-serif'],
      },
      colors: {
        surface: {
          dark: '#0a0f1f',
          'dark-raised': '#121a2e',
          light: '#f6f7fb',
          'light-raised': '#ffffff',
        },
        glass: {
          DEFAULT: 'rgba(255,255,255,0.05)',
          hover: 'rgba(255,255,255,0.08)',
          light: 'rgba(255,255,255,0.65)',
          'light-hover': 'rgba(255,255,255,0.85)',
        },
        border: {
          DEFAULT: 'rgba(255,255,255,0.10)',
          light: 'rgba(15,23,42,0.08)',
        },
        // Primary accent: blue (#3B82F6) -> secondary: cyan (#06B6D4).
        // Reserved for primary buttons, progress bars, active nav, focus
        // rings, selected icons — not used as a general decorative wash.
        accent: {
          50: '#eff6ff',
          100: '#dbeafe',
          200: '#bfdbfe',
          300: '#93c5fd',
          400: '#60a5fa',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
          // Secondary accent endpoint (cyan), used for gradients — kept as
          // `glow` (not `cyan`) since every gradient/shadow utility across
          // the app already references accent-glow.
          glow: '#06b6d4',
        },
        success: '#22c55e',
        warning: '#f59e0b',
        danger: '#ef4444',
      },
      borderRadius: {
        '4xl': '1.75rem',
      },
      boxShadow: {
        soft: '0 8px 32px rgba(0,0,0,0.35)',
        'soft-lg': '0 20px 60px -10px rgba(0,0,0,0.45)',
        'soft-light': '0 8px 32px rgba(15,23,42,0.12)',
        glow: '0 0 30px rgba(59,130,246,0.15)',
        'glow-sm': '0 0 16px rgba(59,130,246,0.18)',
      },
      keyframes: {
        'fade-in': { '0%': { opacity: 0 }, '100%': { opacity: 1 } },
        'fade-in-up': {
          '0%': { opacity: 0, transform: 'translateY(8px)' },
          '100%': { opacity: 1, transform: 'translateY(0)' },
        },
        shimmer: { '0%': { backgroundPosition: '-200% 0' }, '100%': { backgroundPosition: '200% 0' } },
        'pulse-glow': { '0%, 100%': { opacity: 1 }, '50%': { opacity: 0.45 } },
        float: {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%': { transform: 'translateY(-6px)' },
        },
      },
      animation: {
        'fade-in': 'fade-in 0.25s ease-out',
        'fade-in-up': 'fade-in-up 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
        shimmer: 'shimmer 2.5s linear infinite',
        'pulse-glow': 'pulse-glow 2.2s ease-in-out infinite',
        float: 'float 4s ease-in-out infinite',
      },
      backgroundImage: {
        // Radial glow layers over the base surface gradient, combined into
        // one value — `background-image` utilities can't be stacked, so
        // this is the full dark-mode background in a single token.
        'grid-glow':
          'radial-gradient(circle at 15% -10%, rgba(59,130,246,0.14), transparent 45%), radial-gradient(circle at 85% 0%, rgba(6,182,212,0.10), transparent 40%), linear-gradient(180deg, #0a0f1f 0%, #101827 100%)',
        'surface-gradient': 'linear-gradient(180deg, #0a0f1f 0%, #101827 100%)',
      },
    },
  },
  plugins: [],
}
