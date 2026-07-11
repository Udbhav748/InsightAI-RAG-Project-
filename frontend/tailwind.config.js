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
        primary: {
          50: '#eef2ff',
          100: '#e0e7ff',
          500: '#6366f1',
          600: '#4f46e5',
          700: '#4338ca',
        },
        surface: {
          dark: '#0b1220',
          'dark-raised': '#101a2c',
          light: '#f6f7fb',
          'light-raised': '#ffffff',
        },
        glass: {
          DEFAULT: 'rgba(255,255,255,0.06)',
          hover: 'rgba(255,255,255,0.09)',
          light: 'rgba(255,255,255,0.65)',
          'light-hover': 'rgba(255,255,255,0.85)',
        },
        border: {
          DEFAULT: 'rgba(255,255,255,0.12)',
          light: 'rgba(15,23,42,0.08)',
        },
        accent: {
          50: '#eefbff',
          100: '#d9f5ff',
          200: '#b3ecff',
          300: '#7ddcff',
          400: '#38c8fb',
          500: '#0ea5e9',
          600: '#0284c7',
          700: '#0369a1',
          glow: '#22d3ee',
        },
      },
      borderRadius: {
        '4xl': '1.75rem',
      },
      boxShadow: {
        soft: '0 8px 30px -12px rgba(0,0,0,0.25)',
        'soft-lg': '0 20px 60px -15px rgba(0,0,0,0.45)',
        'soft-light': '0 8px 30px -12px rgba(15,23,42,0.12)',
        glow: '0 0 0 1px rgba(56,200,251,0.35), 0 0 28px -6px rgba(56,200,251,0.55)',
        'glow-sm': '0 0 16px -4px rgba(56,200,251,0.45)',
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
        'fade-in': 'fade-in 0.3s ease-out',
        'fade-in-up': 'fade-in-up 0.35s cubic-bezier(0.16, 1, 0.3, 1)',
        shimmer: 'shimmer 2.5s linear infinite',
        'pulse-glow': 'pulse-glow 2.2s ease-in-out infinite',
        float: 'float 4s ease-in-out infinite',
      },
      backgroundImage: {
        'grid-glow':
          'radial-gradient(circle at 20% 0%, rgba(56,200,251,0.15), transparent 45%), radial-gradient(circle at 80% 10%, rgba(99,102,241,0.12), transparent 40%)',
      },
    },
  },
  plugins: [],
}
