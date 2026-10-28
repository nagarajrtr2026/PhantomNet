import { Analytics } from '@vercel/analytics/next'
import type { Metadata, Viewport } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'PhantomNet | Security Operations',
  description: 'Security analyst dashboard for PhantomNet generative cyber-deception telemetry.',
  generator: 'PhantomNet',
}

export const viewport: Viewport = { colorScheme: 'dark', themeColor: '#080a0d', userScalable: false }

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en" className="dark"><body className="antialiased">{children}{process.env.NODE_ENV === 'production' && <Analytics />}</body></html>
}
