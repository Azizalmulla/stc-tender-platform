/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  images: {
    unoptimized: true, // Fix for static image loading in Vercel
  },
  async rewrites() {
    // Only add rewrites if API URL is configured
    if (process.env.NEXT_PUBLIC_API_URL) {
      return [
        {
          source: '/api/:path*',
          destination: process.env.NEXT_PUBLIC_API_URL + '/api/:path*',
        },
      ];
    }
    return [];
  },
};

module.exports = nextConfig;
