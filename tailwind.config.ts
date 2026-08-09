import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        ink: '#111318',
        paper: '#f7f7f5',
        accent: '#ff5c39',
      },
    },
  },
  plugins: [],
};
export default config;
