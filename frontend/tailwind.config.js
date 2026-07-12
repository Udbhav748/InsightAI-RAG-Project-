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
          dark: '#0b0b0d',
          'dark-secondary': '#111315',
          'dark-panel': '#17191c',
          light: '#f6f7fb',
          'light-raised': '#ffffff',
        },
        // Soft elevated surfaces (the default for most cards — no blur).
        card: {
          DEFAULT: 'rgba(255,255,255,0.03)',
          hover: 'rgba(255,255,255,0.05)',
          light: 'rgba(255,255,255,0.75)',
          'light-hover': 'rgba(255,255,255,0.92)',
        },
        border: {
          DEFAULT: 'rgba(255,255,255,0.08)',
          light: 'rgba(15,23,42,0.08)',
        },
        ink: {
          primary: '#f5f5f5',
          secondary: '#b4b8c2',
          muted: '#7c8391',
        },
        // Single restrained accent (emerald). Used only for primary
        // actions, focus rings, active navigation, and status/success —
        // never as a decorative wash or gradient.
        accent: {
          50: '#ecfdf5',
          100: '#d1fae5',
          200: '#a7f3d0',
          300: '#6ee7b7',
          400: '#34d399',
          500: '#10b981',
          600: '#059669',
          700: '#047857',
        },
        success: '#10b981',
        warning: '#f59e0b',
        danger: '#ef4444',
      },
      borderRadius: {
        // Panel-level radius (16–20px range); left the global xl/2xl/3xl
        // scale untouched so small controls (buttons, badges) stay compact.
        panel: '1.125rem',
      },
      boxShadow: {
        soft: '0 8px 24px rgba(0,0,0,0.25)',
        'soft-lg': '0 12px 32px rgba(0,0,0,0.3)',
        'soft-light': '0 8px 24px rgba(15,23,42,0.1)',
      },
      keyframes: {
        'fade-in': { '0%': { opacity: 0 }, '100%': { opacity: 1 } },
        'fade-in-up': {
          '0%': { opacity: 0, transform: 'translateY(6px)' },
          '100%': { opacity: 1, transform: 'translateY(0)' },
        },
        shimmer: { '0%': { backgroundPosition: '-200% 0' }, '100%': { backgroundPosition: '200% 0' } },
        'pulse-soft': { '0%, 100%': { opacity: 1 }, '50%': { opacity: 0.5 } },
      },
      animation: {
        'fade-in': 'fade-in 0.2s ease-out',
        'fade-in-up': 'fade-in-up 0.25s cubic-bezier(0.16, 1, 0.3, 1)',
        shimmer: 'shimmer 2.5s linear infinite',
        'pulse-soft': 'pulse-soft 2s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
