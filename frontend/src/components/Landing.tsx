import { Leaf } from './Onboarding'

// NASA "Blue Marble" photo taken by the Apollo 17 crew, 1972 (public domain)
const EARTH_IMG =
  'https://upload.wikimedia.org/wikipedia/commons/thumb/9/97/The_Earth_seen_from_Apollo_17.jpg/960px-The_Earth_seen_from_Apollo_17.jpg'

const GASES = [
  {
    formula: 'CO₂',
    name: 'Carbon dioxide',
    from: 'Burning petrol, diesel, coal and gas: vehicles, electricity, cooking fuel.',
    power: 'The baseline: 1×',
  },
  {
    formula: 'CH₄',
    name: 'Methane',
    from: 'Livestock (especially cattle and sheep), rice paddies, landfills, gas leaks.',
    power: '~28× more heat-trapping than CO₂',
  },
  {
    formula: 'N₂O',
    name: 'Nitrous oxide',
    from: 'Fertilisers in farming and some industrial processes.',
    power: '~270× more heat-trapping than CO₂',
  },
]

const STEPS = [
  { title: 'Analyze', text: 'Tell the AI assistant what you did, or upload an electricity bill or receipt.' },
  { title: 'Understand', text: 'See your footprint in CO₂e, where it comes from, and how you compare.' },
  { title: 'Reduce', text: 'Get actions ranked by how much CO₂ they save you, set a goal and track it.' },
]

export function Landing({ onStart }: { onStart: () => void }) {
  return (
    <div className="min-h-screen bg-[#05080f] text-white">
      {/* Hero */}
      <section className="relative overflow-hidden">
        <img
          src={EARTH_IMG}
          alt="Planet Earth photographed from space by the Apollo 17 crew"
          className="pointer-events-none absolute top-1/2 mix-blend-screen right-[-12rem] w-[42rem] max-w-none -translate-y-1/2 opacity-70 select-none sm:right-[-6rem] lg:right-0 lg:w-[38rem] lg:opacity-90"
        />
        <div className="absolute inset-0 bg-gradient-to-r from-[#05080f] via-[#05080f]/85 to-transparent" />
        <div className="relative mx-auto flex min-h-[92vh] max-w-6xl flex-col justify-center px-6 py-16">
          <div className="flex items-center gap-2 text-emerald-400">
            <Leaf />
            <span className="font-semibold tracking-tight">EcoTrack</span>
          </div>
          <h1 className="mt-6 max-w-2xl text-4xl leading-tight font-semibold tracking-tight sm:text-6xl">
            Our planet is warming. <span className="text-emerald-400">Your choices count.</span>
          </h1>
          <p className="mt-5 max-w-xl text-lg text-slate-300">
            EcoTrack is an AI agent that measures your carbon footprint from everyday life, shows you where it comes
            from, and tells you exactly what to change first.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-4">
            <button
              onClick={onStart}
              className="rounded-xl bg-emerald-500 px-7 py-3.5 text-base font-semibold text-[#05080f] shadow-lg shadow-emerald-500/20 hover:bg-emerald-400"
            >
              Get started →
            </button>
            <a href="#learn" className="text-sm text-slate-300 underline-offset-4 hover:text-white hover:underline">
              What are greenhouse gases?
            </a>
          </div>
          <dl className="mt-14 grid max-w-xl grid-cols-3 gap-6">
            {[
              ['420+ ppm', 'CO₂ in the air today, up from ~280 before industry'],
              ['~2 t', 'yearly CO₂ per person in India'],
              ['2.3 t', 'per-person level to aim for by 2030 (1.5 °C path)'],
            ].map(([value, label]) => (
              <div key={value}>
                <dt className="text-2xl font-semibold text-white">{value}</dt>
                <dd className="mt-1 text-xs leading-snug text-slate-400">{label}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      {/* Greenhouse gases explained */}
      <section id="learn" className="border-t border-white/10 bg-[#070c16]">
        <div className="mx-auto max-w-6xl px-6 py-16">
          <h2 className="text-3xl font-semibold tracking-tight">What are greenhouse gases?</h2>
          <p className="mt-3 max-w-3xl text-slate-300">
            Sunlight warms the Earth, and the Earth gives that heat back off towards space. Greenhouse gases in the air
            trap part of that heat, like a blanket. Some is natural and keeps us alive, but burning fuel and some kinds
            of farming have thickened the blanket, so the planet keeps warming.
          </p>

          <div className="mt-10 grid gap-4 md:grid-cols-3">
            {GASES.map((g) => (
              <div key={g.formula} className="rounded-2xl border border-white/10 bg-white/[0.03] p-6">
                <div className="text-3xl font-semibold text-emerald-400">{g.formula}</div>
                <div className="mt-1 font-medium">{g.name}</div>
                <p className="mt-3 text-sm text-slate-300">{g.from}</p>
                <p className="mt-3 text-xs font-medium text-amber-300">{g.power}</p>
              </div>
            ))}
          </div>

          <div className="mt-6 rounded-2xl border border-emerald-400/30 bg-emerald-400/5 p-6">
            <div className="font-semibold">So what is “CO₂e”?</div>
            <p className="mt-2 text-sm text-slate-300">
              To add different gases together, each one is converted into the amount of CO₂ that would cause the same
              warming: its <strong className="text-white">CO₂-equivalent</strong>. 1 kg of methane counts as about 28 kg
              CO₂e. Every number in EcoTrack is in CO₂e, calculated with published emission factors (India&apos;s CEA,
              UK DEFRA, IPCC), never guessed by the AI.
            </p>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="border-t border-white/10">
        <div className="mx-auto max-w-6xl px-6 py-16">
          <h2 className="text-3xl font-semibold tracking-tight">How EcoTrack works</h2>
          <div className="mt-10 grid gap-4 md:grid-cols-3">
            {STEPS.map((s, i) => (
              <div key={s.title} className="rounded-2xl border border-white/10 bg-white/[0.03] p-6">
                <div className="grid size-9 place-items-center rounded-full bg-emerald-500 font-semibold text-[#05080f]">
                  {i + 1}
                </div>
                <div className="mt-4 text-lg font-semibold">{s.title}</div>
                <p className="mt-2 text-sm text-slate-300">{s.text}</p>
              </div>
            ))}
          </div>
          <div className="mt-12 flex flex-col items-center gap-3 text-center">
            <p className="text-slate-300">It takes under a minute to log your first day.</p>
            <button
              onClick={onStart}
              className="rounded-xl bg-emerald-500 px-7 py-3.5 font-semibold text-[#05080f] hover:bg-emerald-400"
            >
              Get started →
            </button>
          </div>
        </div>
      </section>

      <footer className="border-t border-white/10 px-6 py-6 text-center text-xs text-slate-500">
        Earth photo: NASA, Apollo 17 (public domain). Emission factors are approximate; figures are estimates.
      </footer>
    </div>
  )
}
