import { useEffect } from 'react'
import LandingNav from '../components/landing/LandingNav'
import Hero from '../components/landing/Hero'
import Features from '../components/landing/Features'
import LiveDemo from '../components/landing/LiveDemo'
import TechStack from '../components/landing/TechStack'
import HowItWorks from '../components/landing/HowItWorks'

export default function LandingPage() {
  // Enable one-section-per-screen scroll-snap only while the landing is mounted.
  useEffect(() => {
    document.documentElement.classList.add('landing-snap')
    return () => document.documentElement.classList.remove('landing-snap')
  }, [])

  return (
    <div className="relative min-h-screen overflow-x-clip bg-[#fbfbfe] text-zinc-700 transition-colors duration-300 dark:bg-transparent dark:text-zinc-300">
      <LandingNav />
      <main>
        <Hero />
        <Features />
        <LiveDemo />
        <TechStack />
        <HowItWorks />
      </main>
    </div>
  )
}
