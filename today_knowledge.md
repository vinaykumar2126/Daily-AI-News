# Daily briefing knowledge — 2026-10-11

## Opening narrative (what the agent delivers first)
Good morning. Here's your briefing for Sunday, October 11.

First up, AI & Tech.

OpenAI is rolling out an Ultrafast mode for GPT-six-point-one Sol in the API, Codex, and ChatGPT Work. The feature offers intelligence described as near-Astra-level at up to eight times the speed of Sol Standard. API pricing for the Ultrafast mode is twelve dollars per million input tokens and sixty dollars per million output tokens.

Google introduced a universal Gemini agent designed to autonomously handle knowledge work, media creation, coding, and multi-step workflows. It integrates with Workspace and other enterprise tools, and adds features like persistent context, multi-agent orchestration, and cost controls.

NVIDIA has released a research repository called LongLive, which includes code and model weights for long video generation and world-action modeling. The release contains several distinct projects, including Long-WAM for training robot policies, LongLive 2.0, which is an infrastructure for fast training and serving of long-video models using N-V-F-P-four quantization, and a project for real-time interactive long video generation.

Microsoft has open-sourced Quicksand, an async Python API for launching and controlling sandboxed AI agents in QEMU virtual machines. It provides pre-built Linux VMs, supports x-eighty-six sixty-four and ARM-sixty-four architectures, and runs on macOS, Linux, and Windows without requiring root privileges or Docker.

A new open-source personal AI agent called Talorys is now available, designed to be self-hosted entirely on a user's own Cloudflare free-tier account. It offers chat, memory, task management, and automations, running on Cloudflare's stack including Workers AI and Durable Objects.

Anthropic has launched a Cyber Mission initiative, which includes a new tool called OSS Scanner. It offers open-source projects free, regular security scans using Anthropic's strongest models. The initiative also includes a program to help secure critical infrastructure.

From Exa dot ai, a new benchmark called ATLAS evaluates search agents on real-world tasks that require web searches. The benchmark revealed that even high-effort agents miss significant correct answers, suggesting major room for improvement in search engines.

A recent project report detailed how AI agents were used to decompile a first-person shooter to C plus plus, a process that consumed over five hundred billion tokens. The orchestration involved models like Claude Max and Sonnet 5, using GitHub for issue tracking, Discord for communication, and Hex-Rays' ida-mcp for the core decompilation.

A new analysis explains the mechanics of speculative decoding. The technique uses a small draft model to propose a token sequence, which a larger model then verifies in a single parallel pass. This can speed up generation by using available compute, particularly with small batch sizes, but may waste compute at high throughput.

Finally, a report from Epoch AI concluded that current AI models cannot yet autonomously produce Epoch-quality research work. While frontier models handled well-defined tasks, they failed at open-ended aspects, and open-weight models struggled even with the well-defined tasks.

Next, US Headlines.

A bipartisan group of seven senators on the Foreign Relations Committee has condemned a recent deal by former President Trump and Russian President Vladimir Putin. The deal would lift sanctions and permit Russian oil into the global market, which the lawmakers noted goes against a 2022 congressional ban on Russian energy imports.

In the Great Plains, high diesel prices are causing some voters to rethink their political choices ahead of the midterm elections. In Iowa, a state where Republicans have long dominated, some voters now say they are considering all of their options.

The Federal Trade Commission, or FTC, is sending fifteen-point-eight million dollars to more than two million users of a cash advance app. The agency says people should check their email for information on the payments.

Tropical Storm Rachel has been downgraded after causing flooding and damage in southern California over the weekend. The storm's remnants are now moving inland, bringing record rain to Las Vegas and flood watches to Utah, while forecasters warn it may be a preview of a record-setting El Niño winter for California.

Turning to Immigration & Visas.

(no output)

And finally, Markets.

The major indices all moved up. The S and P five hundred rose about zero point six percent, as did the Nasdaq Composite. The Dow Jones was up about zero point eight percent. On your watchlist, moves were mixed. Amazon was up about three point three percent, Microsoft rose about two point four percent, and Google was up just under one percent. Meanwhile, Apple was down about one point one percent, and Nvidia was down about half a percent.

That's your briefing. Have a great day.

## Source stories (grounding for follow-up questions)

### AI & Tech
- Ultrafast is rolling out today for GPT-6.1 Sol in the API, Codex, and ChatGPT Work — OpenAI is rolling out Ultrafast today for GPT-6.1 Sol in the API, Codex, and ChatGPT Work. The feature offers near-Astra-level intelligence at up to 8x faster speeds than Sol Standard. It is built for work where speed and intelligence make a difference. API pricing for GPT-6.1 Sol in Ultrafast mode is $12 per million input tokens and $60 per million output tokens.
- Gemini Agent — Google introduced a universal Gemini agent that could autonomously handle knowledge work, media creation, coding, and multi-step workflows across Workspace and other enterprise tools. It also added persistent context, multi-agent orchestration, model routing, governance, and cost controls.
- Former Cognition, Ramp Staffers Want AI Agents Running Businesses — Hone, a startup formed by a group of former employees from some of the fastest-growing AI firms, has raised a $60 million seed round. The startup aims to create AI agents that can help run a business, essentially serving as professional staffers. These agents will be able to field long-running tasks that run over the course of weeks or even months. The five-month-old startup joins a growing number of companies selling AI software to businesses that promise to automate complex work.
- Can AI automate Epoch? — Epoch Automation Reports show that models can't yet autonomously produce Epoch-quality work. Frontier models performed reliably on well-defined tasks, but they failed in the more open-ended aspects that prevent full automation. Open-weight models lag further behind, struggling even on the well-defined tasks that frontier models handle reliably.
- Why is Speculative Decoding Fast? — Speculative Decoding is a technique where a small draft model proposes a likely draft sequence, and a big model verifies that sequence in parallel in a single forward pass. It enables the ability to look at many tokens at once and accept the ones that would have been generated by the big model. When the batch size is smaller than the optimal number of tokens, speculative decoding allows models to use 'free' compute to complete sequences faster.
- ATLAS: Evaluating Agents on Search-Intensive Tasks — ATLAS is a new benchmark that evaluates search agents on real-world tasks requiring web searches, highlighting their accuracy and completeness. The benchmark reveals that even high-effort agents miss significant golden answers, indicating major room for improvement in search engines. ATLAS differs from existing benchmarks by focusing on non-memorized tasks, requiring extensive multi-domain searches, and offering a cost-effective grading process.
- Product Manager, Applied AI at TLDR — TLDR is hiring its first PM to help build the agent-first operating layer used across the company. We're looking for a builder who has shipped real products/systems with LLMs. Click here to learn more .
- Quicksand
- NVIDIA's Long-Video and World-Action Research — <!--
SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. SPDX-License-Identifier: Apache-2.0
Provenance: Modified from NVlabs/LongLive. Source: https://github.com/NVlabs/LongLive @ fb16a87 :: README.md
Changes: Add the independent Long-WAM project and its entry points.
- OpenAI's revenue is reportedly $20 billion less than previously projected — OpenAI has told its investors that its annualized revenue is approaching $50 billion, $20 billion less than a figure reported a little over a week ago. The previously reported figure was devised by OpenAI investors as an attempt to produce a direct comparison with Anthropic's annualized revenues. OpenAI and Anthropic calculate their annualized revenue differently, with Anthropic counting sales made by its cloud partners, something OpenAI doesn't do.
- OpenAI Cannot Make AI Safe on Its Own — Three former OpenAI safety researchers say their dismissals risk chilling internal dissent and external collaboration. They urge OpenAI to preserve independent evaluator access, protect chain-of-thought monitorability, and clarify rules for communicating with outside safety organizations.
- Anthropic Cyber Defense Initiative — Introducing the Anthropic Cyber Mission \ Anthropic Announcements Introducing the Anthropic Cyber Mission Oct 8, 2026 Today we’re launching the Anthropic Cyber Mission, a long-term commitment to securing the systems everyone depends on. The Cyber Mission is a new effort to support defenders with tools, research, and resources to secure their software and systems.
- Talorys – A self-hosted personal AI agent on Cloudflare's free tier — # Talorys **Your personal AI agent. Your own cloud.** Talorys is a free, open-source personal AI assistant that runs entirely inside
**your own Cloudflare account**. It chats with you, remembers what matters,
manages tasks, notes and projects, and runs reminders and routines on a
schedule — without any server, database or account operated by the Talorys
developers. One person. One Cloudflare account. One command. One personal AI agent. ```bash
npx create-talorys@latest
``` --- ## 1.
- Show HN: WallHop – 12ft.io is gone, so I built a replacement
- The gap in shared understanding of LLM capability is widening
- Show HN: BetterWispr – Free, open-source dictation for Mac
- 500B tokens later: Letting AI agents decompile a first-person shooter — 500+ Billion Tokens Later: Letting AI Agents Decompile A First-Person Shooter | Maurice's Blog During the last 3 months, I spent some of my time and tokens decompiling a popular first-person shooter. The goal was not to reach a simple proof-of-concept state. Instead, we really wanted an accurate, stable and feature-complete recreation of the game. The avid reader of my blog might have noticed that I had previously written two posts that have since been removed.
- My personal AI agent posted my bank details on company Slack
- Ask HN: Why aren't Americans rising up against tipping?
- Will the HomeView be Apple’s first smart home success? — Over the past couple of years, we’ve seen multiple reports that Apple was working on a new smart home product, but now it seems the product has a name and a launch date.
- Aaron Sorkin’s ‘Social Reckoning’ is off to a weak start — What does this mean for a fall full of movies starring villainous tech CEOs?
- A college in Illinois tried to cancel its Flock contact and it refused — In April of 2025, Elgin Community College had six Flock safety cameras installed to "enhance the safety and security of students." But by September of that year, the school's administration grew concerned that Flock was sharing data with Customs and Border Patrol, that camera feeds were not properly secured, and that both law enforcement and […]
- 48 hours to TechCrunch Disrupt 2026 — hear directly from the people building what’s next — Less than 48 hours, TechCrunch Disrupt 2026 starts in San Francisco’s Moscone West. Save up to $100 on your pass before prices increase at the door, plus get 50% on a second pass. Or score other deals.
- Silicon Valley is falling in line with Trump’s attempt to rename AI — When President Donald Trump announced his plans to rebrand artificial intelligence as "super intelligence," you'd be forgiven for being skeptical that it would catch on. While most of the broader population is sticking with AI, some of Silicon Valley's most powerful are falling in line and trying to give Trump the great AI rebrand he […]
- The investor’s guide to TechCrunch Disrupt 2026: Everything you need to know — Year after year, investors who've explored the Expo Halls, met founders, and learned from peers have proven why you need to be on the ground at Disrupt Oct. 13.
- The new Apple TV could have a built-in mic and a remote with a speaker — The latest rumors are that the new Apple TV will have a built-in microphone, while the upgraded remote will get a speaker. The mic would let users control the set-top box using Siri without having to speak into the remote or a connected HomePod device. That could also let the Apple TV serve as a […]
- Can the AI industry persuade data center opponents by getting rid of NDAs? — On Equity, we debate the impact of data center moratoriums and whether the AI industry has a communication problem.
- NASA dumped over 800GB of Artemis II data online — If you thought you'd seen all there is to see from the Artemis II mission, you're wrong. This week NASA posted over 800GB worth of science data, images, and videos on the Artemis II: Sights & Sounds of Science site. The archive includes over 11,000 photos and videos, over 8.5 hours of audio, and crew-annotated […]
- George A. Romero’s Season of the Witch is a slow-burn feminist occult drama — George A. Romero is obviously best known as the father of the modern zombie movie. But between inventing the genre with Night of the Living Dead and his outbreak horror, The Crazies, Romero made two much lesser-known films: There's Always Vanilla, which I'll admit I've never seen, and Season of the Witch, or, as it […]

### US Headlines
- Hurricane Simon lashes Mexico's Pacific coast as a powerful Category 3 storm — Simon skirted along Mexico's Pacific coast as a major hurricane on Sunday.
- As high diesel prices hit Great Plains, some considering all options in midterms — Republicans have dominated elections in Great Plains states for a generation. But with the midterms fast approaching, Ed O'Keefe reports that some voters in Iowa now say they're considering all of their options.
- Terminal in Riyadh airport hit again, a day after deadly strike killed 12 — The strike on King Khalid International Airport, the deadliest on Saudi soil in more than a decade, marked a major escalation in the war between Yemen's Iran-backed Houthis and the kingdom.
- Tropical Storm Rachel downgraded as high winds and rain turn inward
- Lawmakers in bipartisan statement push back on Trump over Russian oil — A bipartisan group of seven lawmakers on the Senate Foreign Relations Committee condemned President Trump’s recent deal with Russian President Vladimir Putin, which would lift sanctions on Russia and permit the flow of its oil into the global economy. “Congress explicitly banned Russian energy imports in 2022 to prevent American dollars from financing Putin’s brutal...
- Check your email: $15.8 million being sent to users of cash advance app, FTC says — More than 2 million payments are being sent out, according to the FTC.
- 70 marathon runners evacuated after being stranded by heavy rain: Officials — About 70 runners and volunteers participating in Utah's Moab 240 ultramarathon were stranded overnight after encountering a significant storm.
- Chair of Texas Democratic Party says 'we're full steam ahead' after Talarico's flu recovery — Kendall Scudder, the chair of the Texas Democratic Party, said Sunday he is confident in Texas Democratic Senate candidate James Talarico’s campaign in the wake of his illness. “We're full steam ahead. And, of course, you're going to see people in the swamps of the internet making up conspiracy theories. That's what they always do,”...

### Immigration & Visas
- ICE agent strikes man with vehicle during pursuit in Texas, officials say — Parra-Hernandez suffered a broken leg and taken to a hospital after being hit by car during an ICE operation An Immigration and Customs Enforcement ( ICE ) agent driving a vehicle struck a man on Saturday while trying to pursue him and someone else in the Houston area, according to authorities. The federal agency had been trying to pull over and arrest Jose Mendoza-Cervantes in north-west Harris county, Texas , when he and the victim, Miguel Parra-Hernandez, exited the vehicle, officials said.
- ‘Deeply concerning’: Democratic congressional candidate rebukes ICE’s presence in New York — Darializa Avila Chevalier criticizes NYPD’s ‘inaction’ in protecting Marble Hill protesters after ICE shot a man Democratic congressional candidate Darializa Avila Chevalier believes that the New York police departments’ conduct towards protesters after an ICE agent shot and wounded a man in the district she is running to represent violated “the spirit, if not the letter” of the city’s sanctuary laws .
- Despair after 200-year-old ‘grandmother’ tree toppled for Trump’s border wall: ‘It crushes your heart’ — Protesters spent months occupying an ancient cottonwood. Then a tense standoff with US border patrol came to a head A 200-year-old cottonwood tree near the US-Mexico border , known as the “grandmother”, has been destroyed to make way for the construction of Donald Trump ’s border wall, despite a months-long effort by protesters trying to save it. In late July, land defenders began a tree-sit in the ghost town of Lochiel, Arizona , taking turns occupying a platform high in the tree’s canopy.
- US man shoots off-duty ICE agent who allegedly attacked him and daughter — ICE official, who was sleeping on man’s lawn and appeared ‘intoxicated’, faces felony charges, California police say A 72-year-old man shot an off-duty Immigration and Customs Enforcement ( ICE ) official in California early on Friday morning after the “intoxicated and agitated” official assaulted him and his daughter on their property, local authorities allege. The Fresno police department said that the ICE official was receiving medical care after being shot in the midsection.

### Markets
- Index moves — S&P 500: 7,812 (+0.59%); Nasdaq Composite: 27,366 (+0.64%); Dow Jones: 51,655 (+0.83%)
- Watchlist moves — AMZN +3.29%; MSFT +2.38%; AAPL -1.11%; GOOGL +0.97%; NVDA -0.52%

