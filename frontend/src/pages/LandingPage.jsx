import HomeNav from '../components/home/HomeNav'
import Hero from '../components/home/Hero'
import FeatureStrip from '../components/home/FeatureStrip'
import Features from '../components/home/Features'
import HowItWorks from '../components/home/HowItWorks'
import About from '../components/home/About'
import HomeFooter from '../components/home/HomeFooter'

export default function LandingPage() {
  return (
    <div className="relative min-h-[100dvh] overflow-x-clip bg-ink-950 text-zinc-300">
      <HomeNav />
      <main>
        <Hero />
        <FeatureStrip />
        <Features />
        <HowItWorks />
        <About />
      </main>
      <HomeFooter />
    </div>
  )
}
