"""
Knowledge Base Seeder.

Indexes exercise science, nutrition, and swimming knowledge into the embeddings
table so the Knowledge Agent can do RAG (Retrieval-Augmented Generation).

This prevents LLM hallucinations by grounding responses in verified domain knowledge.

Run with:
    .venv/bin/python scripts/seed_knowledge_base.py

NOTE: Requires a valid OPENAI_API_KEY in .env (for generating embeddings).
"""

import asyncio
import os
import sys
from uuid import uuid4

# Load .env before anything else
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

import os; DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://akshay@localhost:5432/fitnessos")
engine = create_async_engine(DATABASE_URL, echo=False)

# ─── Knowledge Documents ─────────────────────────────────────────────────────
# Each entry: (title, content, category, tags)
KNOWLEDGE_DOCS = [
    # ── Fat Loss Science ───────────────────────────────────────────────
    (
        "Fat Loss: Caloric Deficit Fundamentals",
        """Fat loss occurs when energy expenditure exceeds energy intake (caloric deficit).
A deficit of 500 kcal/day produces approximately 0.5kg of fat loss per week.
A deficit of 750-1000 kcal/day produces 0.75-1kg/week — the safe maximum for preserving muscle.
Aggressive deficits (>1000 kcal/day) increase muscle loss and hormonal disruption.
For a 100kg male at moderate activity: TDEE ≈ 2800-3200 kcal/day.
Recommended intake for fat loss: 2000-2400 kcal/day (600-800 kcal deficit).
Never drop below 1600 kcal/day without medical supervision.
Refeed days (eating at maintenance every 7-10 days) help prevent metabolic adaptation.""",
        "fat_loss",
        ["calories", "deficit", "fat_loss", "nutrition"]
    ),
    (
        "Protein Requirements for Fat Loss with Muscle Retention",
        """During a caloric deficit, protein requirements increase to preserve muscle mass.
Recommended intake: 1.6-2.2g of protein per kg of body weight.
For a 100kg male: 160-220g protein/day is optimal for muscle retention.
Higher protein (2.0-2.4g/kg) during aggressive deficits provides greater muscle protection.
Protein has the highest thermic effect of food (TEF) at 25-30% — eating protein burns more calories during digestion.
Distribute protein evenly across 4-5 meals (30-40g per meal) for optimal muscle protein synthesis (MPS).
Leucine threshold for MPS: 2.5-3g leucine per meal, found in 25-30g of whey protein or 40-50g of paneer.
Vegetarian high-protein sources: paneer (18g/100g), Greek yogurt (9g/100g), whey (74g/100g), chickpeas (9g/100g cooked), moong dal (7g/100g cooked).""",
        "nutrition",
        ["protein", "muscle_preservation", "fat_loss", "macros"]
    ),
    (
        "Carbohydrate Strategy for Fat Loss",
        """Carbohydrates are NOT the enemy — total calories determine fat loss, not carb intake alone.
Carbs fuel gym performance and swimming — removing them entirely degrades training quality.
Recommended carb intake for active individuals in deficit: 2-4g/kg body weight.
For a 100kg person: 200-400g carbs/day depending on training intensity.
Prioritize complex carbs (oats, brown rice, quinoa, sweet potato) over simple carbs.
Time carbs around workouts: consume 30-60g carbs 1-2 hours pre-workout for performance.
Post-workout window: 40-60g carbs within 30-60 minutes helps glycogen replenishment.
Reduce carbs on rest days — shift carbs from rice/roti to vegetables and legumes.
Low-carb days (<100g): prioritize protein and fat, ideal for non-training days.""",
        "nutrition",
        ["carbohydrates", "carb_cycling", "performance", "fat_loss"]
    ),
    (
        "Fat Intake for Hormonal Health",
        """Dietary fat is essential for testosterone production, joint health, and fat-soluble vitamins.
Minimum fat intake: 0.5g/kg body weight to maintain hormonal function.
Recommended: 0.8-1.0g/kg = 80-100g fat/day for a 100kg male.
Sources for vegetarians: ghee, full-fat dairy, nuts (almonds, walnuts), seeds (flax, chia), avocado, coconut oil.
Omega-3 fatty acids reduce inflammation, improve recovery, and support fat loss.
Flaxseeds (plant omega-3) are less bioavailable than fish oil — consider algae-based omega-3 supplements.
Saturated fat from ghee and dairy is acceptable in moderation — not the driver of heart disease when calories are controlled.""",
        "nutrition",
        ["fat", "hormones", "testosterone", "omega3"]
    ),
    (
        "Meal Timing for Training Performance",
        """Pre-workout meal (1-2 hours before): 40-60g carbs + 20-30g protein. Example: oats + whey, rice + paneer, banana + protein shake.
Pre-workout snack (30-45 min before): fast carbs only. Example: banana, dates, rice cakes.
Post-workout window: within 30-60 minutes — 40-60g carbs + 30-40g protein for muscle recovery.
Post-workout examples: whey shake + banana, rice + paneer, Greek yogurt + oats.
Eating eggs only after evening gym (as per user preference) is optimal — eggs are high protein for recovery.
Protein before bed: casein protein or hung curd (200g) supports overnight muscle protein synthesis.
Inter-meal fasting: avoid going more than 4-5 hours without protein to maintain positive nitrogen balance.""",
        "nutrition",
        ["meal_timing", "pre_workout", "post_workout", "performance"]
    ),

    # ── Workout Science ────────────────────────────────────────────────
    (
        "Hypertrophy: Principles of Muscle Building",
        """Muscle hypertrophy requires: mechanical tension, metabolic stress, and muscle damage.
Optimal rep range for hypertrophy: 6-20 reps per set (most evidence supports 8-15 reps).
Sets per muscle group per week: 10-20 sets for hypertrophy (beginners: 10-12, advanced: 15-20).
Frequency: train each muscle group 2x/week minimum for optimal hypertrophy.
Progressive overload is the primary driver — consistently increase weight, reps, or sets over time.
Rest periods: 60-180 seconds for hypertrophy, 180-300 seconds for strength.
Protein synthesis is elevated for 24-48 hours after training — training frequency should reflect this.
V-taper is created by wide shoulders (lateral raises, OHP) + narrow waist + wide back (pull-ups, rows).""",
        "workout_science",
        ["hypertrophy", "muscle_growth", "progressive_overload", "sets_reps"]
    ),
    (
        "Progressive Overload: Evidence-Based Methods",
        """Double progression: increase reps within a range, then increase weight. Example: 6-10 reps — once 10 reps achieved at current weight, add 2.5kg next session.
Linear progression: add fixed weight each session. Works for beginners (0-12 months). Add 2.5kg per session to main lifts.
Percentage-based loading: work at 70-85% of 1RM for hypertrophy, 85-95% for strength.
Epley 1RM formula: 1RM = weight × (1 + reps/30). Example: 80kg × 8 reps = 1RM of ~107kg.
RIR method: always leave 1-3 reps in reserve (RIR). RPE 7-8 = 2-3 RIR. This prevents injury while maintaining intensity.
Volume progression: add one set per week before increasing weight (volume first, then intensity).
Deload every 4-6 weeks: reduce weight by 40-50% and sets by 50% for one week to dissipate fatigue.""",
        "workout_science",
        ["progressive_overload", "1rm", "deload", "periodization"]
    ),
    (
        "V-Taper Training: Shoulder and Back Development",
        """V-taper is the most impactful physique change for aesthetics. Created by:
1. Wide, capped shoulders (deltoids): lateral raises, overhead press, front raises, face pulls.
2. Wide back (latissimus dorsi): pull-ups, lat pulldowns, straight-arm pulldowns.
3. Rear deltoid development: face pulls, reverse flyes, rear delt machine.
4. Lower body fat: visible waist creates illusion of width.

Lateral raises: the most important exercise for V-taper. Train 3-5x/week with 3-5 sets of 15-20 reps.
Use cables for constant tension or dumbbells with controlled movement. No swinging.
Shoulder training frequency can be higher than other muscles (shoulders recover faster).
Overhead press builds shoulder mass — work up to pressing your bodyweight overhead.
Pull-ups build lat width — work toward 10+ strict reps. Add weight when comfortable.""",
        "workout_science",
        ["v_taper", "shoulders", "back", "aesthetics", "lateral_raise"]
    ),
    (
        "Arm Development: Biceps and Triceps",
        """Bigger arms require both biceps AND triceps development (triceps = 2/3 of arm size).
Biceps exercises: barbell curl (mass), hammer curl (brachialis), incline dumbbell curl (long head stretch), spider curl (peak).
Triceps exercises: close-grip bench press, skull crusher, overhead extension (long head), pushdown, dips.
Optimal volume: 10-16 sets per week for biceps, 12-18 sets for triceps.
Rep range: 8-15 for hypertrophy. Use full ROM — stretch at the bottom.
Mind-muscle connection is crucial for arms — focus on the muscle contracting, not just moving weight.
Train arms 2-3x/week — they recover faster than larger muscle groups.
Compound movements (bench press, rows, pull-ups) contribute significantly to arm development.""",
        "workout_science",
        ["biceps", "triceps", "arms", "hypertrophy"]
    ),
    (
        "Chest and Posture Training",
        """Chest development requires pressing from multiple angles: flat (mid chest), incline (upper), decline (lower).
Flat barbell bench press: best overall chest builder. Work toward 1x bodyweight.
Incline dumbbell press: upper chest — essential for a full, thick chest.
Cable flyes: constant tension through full ROM — excellent for stretching the chest fibers.
Posture correction: forward head posture and rounded shoulders are common in desk workers.
Fix posture with: face pulls (3x20), band pull-aparts (3x30), chest stretching, strengthening rhomboids and mid-traps.
Pectoralis minor tightness causes rounded shoulders — stretch regularly.
Avoid over-pressing relative to pulling (aim for 1:1 ratio of pressing to rowing volume).""",
        "workout_science",
        ["chest", "bench_press", "posture", "aesthetics"]
    ),
    (
        "Recovery and Sleep for Muscle Growth",
        """Muscle is built during recovery, not during training. Training is the stimulus, sleep is when growth happens.
Optimal sleep for recovery: 7-9 hours. Growth hormone is primarily released during deep sleep (stages 3-4).
Sleep deprivation (< 6 hours) increases cortisol, reduces testosterone, and impairs muscle protein synthesis by 20-30%.
Prioritizing sleep from 3 AM to 12 AM (current pattern) to midnight to 7 AM (goal) will significantly improve progress.
Post-workout recovery nutrition: carbs + protein within 1 hour.
Active recovery: light walking, swimming at low intensity, yoga help remove lactate and reduce DOMS.
Cold-water immersion (10-15 minutes at 10-15°C) reduces DOMS — available in swimming pools.
Overtraining symptoms: persistent fatigue, decreased performance, irritability, sleep disruption, resting heart rate increase.""",
        "recovery",
        ["sleep", "recovery", "growth_hormone", "overtraining"]
    ),

    # ── Swimming Science ───────────────────────────────────────────────
    (
        "Swimming for Beginners: Getting Started",
        """Swimming is an excellent low-impact cardio and full-body exercise.
Beginner progression:
Week 1-2: Water comfort, floating, basic breathing (face in water).
Week 3-4: Freestyle kick drills with kickboard. Learning to breathe to the side.
Week 5-6: Basic freestyle stroke (1 arm pull, then bilateral breathing).
Week 7-8: Continuous freestyle for 25m without stopping.
Week 9-12: Building to 50m, then 100m without stopping.
Month 3+: Introduce breaststroke and backstroke.
Fear of deep water: stay in shallow end initially. Use pool noodle or kickboard for confidence.
Breathing technique: exhale underwater through nose/mouth, turn head to inhale (not lift).
Practice bilateral breathing (every 3 strokes) for balanced development.""",
        "swimming",
        ["swimming", "beginner", "freestyle", "breathing", "technique"]
    ),
    (
        "Swimming Technique: Freestyle Fundamentals",
        """Freestyle (front crawl) is the fastest and most efficient stroke for fitness.
Body position: flat on water surface, head neutral (eyes down at 45°, not straight down).
Catch phase: reach forward and anchor hand in water — feel the water pressure.
Pull phase: S-shaped pull from in front to behind hip. Elbow high and bent at 90°.
Recovery: exit water near hip, swing arm forward with bent elbow.
Kick: 2-beat, 4-beat, or 6-beat kick. Flutter kick — feet just below surface, minimal knee bend.
Breathing: turn head to the side (not lift). One goggle in, one goggle out.
Common mistakes: lifting head too high to breathe (sinks legs), crossing over centerline (causes body rotation), straight arm pull (less efficient).
Drills: catchup drill, fingertip drag, kicking on side (side kick drill).""",
        "swimming",
        ["freestyle", "technique", "swimming", "stroke"]
    ),
    (
        "Swimming for Fat Loss and Fitness",
        """Swimming burns 400-700 kcal/hour depending on stroke and intensity.
Calories per stroke per hour (approximate, 80kg person): Freestyle: 500-650, Butterfly: 700-900 (not recommended for beginners), Breaststroke: 400-600, Backstroke: 400-500.
HIIT swimming: 25m sprint, 25m easy recovery × 10 = excellent fat burning.
Swimming does NOT cause muscle loss — resistance from water provides hypertrophic stimulus.
Swimming complements gym training by building cardiovascular fitness with minimal joint stress.
Optimal swim frequency for fat loss: 3-4 sessions per week, 30-45 minutes each.
Pool temperature (25-28°C) means the body expends extra calories warming itself.
Morning swims on an empty stomach (fasted cardio) can increase fat oxidation — but may reduce performance.""",
        "swimming",
        ["swimming", "fat_loss", "cardio", "calories"]
    ),

    # ── Indian Vegetarian Nutrition ────────────────────────────────────
    (
        "Indian Vegetarian High-Protein Meal Planning",
        """Vegetarian protein sources (per 100g): whey protein (74g), paneer (18g), Greek yogurt (9g), tempeh (20g), chickpeas/chole cooked (9g), moong dal cooked (7g), quinoa cooked (4.4g), oats (17g raw).
Protein combining: pair grains + legumes for complete amino acid profiles (dal + rice, roti + dal).
Paneer is the most versatile high-protein food for Indian vegetarians — 18g protein per 100g with all essential amino acids.
1 standard serving of paneer (100g) = 18g protein, 265 calories, 21g fat.
Low-fat paneer: 19g protein per 100g, 180 calories — better for fat loss phase.
Whey protein is the most efficient supplement: 74g protein per 100g, rapid absorption, highest leucine content.
Daily meal plan for 160g protein vegetarian: 100g paneer (18g) + 30g whey × 2 (48g) + 200g Greek yogurt (18g) + 3 eggs (39g) + 150g dal (10.5g) + 50g peanuts (13g) = ~147g. Add milk/curd to reach 160g+.
Foods user can eat: milk, paneer, curd, whey protein, protein bars, eggs (post-gym only), no tofu, no soya chunks, no creatine.""",
        "nutrition",
        ["indian_food", "vegetarian", "protein", "meal_planning", "paneer"]
    ),
    (
        "Festival and Travel Nutrition Strategy",
        """During festivals (Diwali, Holi, Dussehra) and travel, maintain 80% compliance rather than perfection.
Strategy: eat protein first at any meal (prioritize paneer, dal, dahi), then eat what you enjoy in moderation.
Damage control at festivals: avoid deep-fried snacks or limit to 1-2 pieces, choose dry sweets over syrupy ones.
Restaurant survival: order grilled paneer tikka, dal, salads. Avoid cream-heavy curries (butter chicken base applies even to veg curries).
Best restaurant protein choices: paneer tikka, dal makhani (lower fat option), rajma, chana masala, tandoori items.
Alcohol at events: if unavoidable, prefer clear spirits (vodka, gin) with soda. Alcohol stops fat oxidation for 24 hours. Avoid beer (liquid carbs).
Day after festival: don't punish yourself. Return to normal eating immediately. Extra gym session optional but not required.
Pre-festival strategy: be in a mild surplus for 1-2 weeks to feel good and improve performance at the event.""",
        "nutrition",
        ["festival", "travel", "nutrition", "restaurants", "indian_food"]
    ),
    (
        "Pre and Post Wedding Physique Plan",
        """Goal: maximum visual impact for photos and wedding day. Focus: low body fat + muscle fullness.
Timeline phases:
6+ months out: focus on building muscle (lean bulk or maintenance + strength training).
3-6 months out: begin gradual fat loss (500-750 kcal deficit). Maintain all training intensity.
8-12 weeks out: moderate deficit, increase training frequency and cardio (swimming).
4 weeks out (pre-wedding shoot Oct 20): aggressive water cut if needed. Eliminate bloat foods (legumes, cruciferous veg, dairy).
1 week out (peak week): carb loading, water manipulation, sodium restriction for max definition.
Peak week protocol:
- Days 1-3: deplete glycogen (low carb: <50g/day).
- Days 4-6: carb load (4-5g/kg = 400-500g carbs from clean sources).
- Day before wedding: moderate carbs, eliminate sodium, drink lots of water then taper.
- Morning of wedding: small carb-rich meal, pump muscles for 10-15 minutes.
Never try anything for the first time peak week — test your body's response weeks earlier.""",
        "goal_planning",
        ["wedding", "peak_week", "physique", "fat_loss", "photos"]
    ),
    (
        "Sleep Optimization for Athletic Performance",
        """Current sleep pattern: 3 AM - 10 AM (7 hours). Goal: 12 AM - 7 AM (7 hours, same duration but earlier).
Sleep timing affects circadian rhythm — later sleep reduces growth hormone release quality.
Strategies to shift sleep earlier:
1. Move bedtime 15 minutes earlier every 3 days (gradual shift takes 3-4 weeks).
2. No screens 30 minutes before target bedtime (blue light delays melatonin).
3. Bright light exposure immediately after waking up (helps reset circadian clock).
4. Exercise before 8 PM — late exercise delays sleep onset.
5. Melatonin 0.5-1mg 30 minutes before target bedtime accelerates the shift.
6. Consistent wake time (7 AM even on weekends) is most powerful sleep timing tool.
Sleep quality markers: feel rested without alarm, dreams remembered, natural morning energy.
Impact on fitness: poor sleep increases cortisol, reduces testosterone, increases hunger hormones (ghrelin), impairs recovery.""",
        "lifestyle",
        ["sleep", "recovery", "circadian_rhythm", "growth_hormone"]
    ),
    (
        "Habit Formation for Consistent Training",
        """Consistency beats intensity — 3 moderate training sessions done consistently outperform sporadic intense sessions.
Habit stacking: attach new habits to existing ones. Example: protein shake → brush teeth → gym bag → go.
Identity-based habits: don't say 'I want to go to gym' — say 'I am someone who trains every evening at 9 PM.'
Minimum viable workout: on days you don't feel like it, commit to just 10 minutes. Usually you'll continue.
Track streaks — losing a streak is psychologically powerful. Don't break the chain.
Weekly adherence target: 80% compliance is excellent. Miss a day? Immediately make a plan for the next one.
Social accountability: sharing goals with someone (or a coach AI) increases adherence by 65%.
Environment design: keep gym bag packed, workout clothes visible, remove friction from the habit.
Reward systems: track milestones (first 10 swim lengths, hit 1 plate on bench) and acknowledge them.""",
        "psychology",
        ["habits", "consistency", "motivation", "adherence", "behavior"]
    ),
]


async def seed_knowledge() -> None:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key or api_key.startswith("sk-REPLACE"):
        print("❌  No valid OPENAI_API_KEY in .env — skipping embedding generation")
        print("   Knowledge base docs will be stored without embeddings.")
        print("   Add your API key and re-run this script to enable semantic search.")
        use_embeddings = False
    else:
        use_embeddings = True

    async with AsyncSession(engine) as session:
        async with session.begin():
            count_result = await session.execute(
                text("SELECT COUNT(*) FROM embeddings WHERE source_type = 'knowledge'")
            )
            existing = count_result.scalar_one()
            if existing > 0:
                print(f"Knowledge base already has {existing} entries. Skipping.")
                return

            if not use_embeddings:
                print("   Skipping knowledge base — re-run after adding OpenAI credits.")
                return

            from langchain_openai import OpenAIEmbeddings
            embed_model = OpenAIEmbeddings(
                model="text-embedding-3-small",
                openai_api_key=api_key,
            )

            inserted = 0
            for title, content, category, tags in KNOWLEDGE_DOCS:
                full_text = f"{title}\n\n{content}"

                try:
                    embedding = embed_model.embed_documents([full_text])[0]
                    embedding_str = f"[{','.join(str(v) for v in embedding)}]"
                except Exception as e:
                    print(f"  ⚠ Embedding failed for '{title}': {e}")
                    continue

                import json as _json
                metadata_json = _json.dumps({"title": title, "category": category, "tags": tags})
                await session.execute(text("""
                    INSERT INTO embeddings (
                        id, user_id, content, source_type, source_id,
                        embedding, embedding_model, chunk_index, chunk_metadata,
                        created_at, updated_at
                    ) VALUES (
                        :id,
                        (SELECT id FROM users WHERE clerk_user_id = 'dev-user-001' LIMIT 1),
                        :content, 'knowledge', NULL,
                        CAST(:embedding AS vector), 'text-embedding-3-small', 0,
                        CAST(:metadata AS jsonb),
                        NOW(), NOW()
                    )
                """), {
                    "id": str(uuid4()),
                    "content": full_text,
                    "embedding": embedding_str,
                    "metadata": metadata_json,
                })
                inserted += 1
                print(f"  ✓  {title}")

        print(f"\n✅  Indexed {inserted} knowledge documents with embeddings")


if __name__ == "__main__":
    asyncio.run(seed_knowledge())
