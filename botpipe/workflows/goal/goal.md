You are implementing a browser-only, early-2000s tactical FPS-inspired multiplayer prototype.

The goal is not to clone Counter-Strike exactly. Do not use copyrighted Counter-Strike assets, names, logos, map files, sounds, textures, models, UI files, weapon models, or exact map layouts. The goal is to create an original browser game that visually and mechanically evokes the Counter-Strike 1.5-era tactical FPS style: low-poly maps, muted colors, angular geometry, readable combat spaces, simple humanoid player models, first-person weapon view, retro HUD, and fast multiplayer deathmatch-style play.

Primary objective:
Create a polished, playable, browser-based multiplayer FPS prototype that feels visually close to an early-2000s tactical shooter while remaining original, lightweight, and fully runnable in a modern browser.

Use generated target reference images as the visual north star before coding, then verify the final browser-rendered game against those references with screenshots and scores.

Core constraints:
1. The game must run fully in the browser.
2. Do not require a native game engine, desktop binary, local executable, or non-browser runtime.
3. Use original assets, original maps, original materials, and original sounds unless a researched free/open asset clearly satisfies the license and visual requirements.
4. Do not use copyrighted Counter-Strike content.
5. The final product must have a complete playable flow:
   menu → map select → join map → play → shoot → take damage → die → respawn → return/change map.
6. The game must support local play and multiplayer presence.
7. The game must be playable with keyboard and mouse.
8. The result must feel like a coherent mini-game, not a generic 3D placeholder scene.
9. Avoid overly complex systems that distract from the core playable prototype.

Reference image phase:
Before implementing the UI or 3D scene, generate a small set of target reference images that define the intended visual direction.

The purpose of these images is not to create final game assets. The purpose is to establish a visual target that the browser game should approximate.

Generate original reference images only. Do not recreate Counter-Strike maps, logos, UI, weapon models, character models, textures, or copyrighted assets. The references should evoke the early-2000s tactical FPS era while remaining fully original.

Reference images to generate:
1. Main menu / map-selection screen.
2. First-person spawn view on the main dusty industrial compound map.
3. Central contested courtyard.
4. Narrow interior corridor route.
5. Flank route with cover.
6. Elevated balcony, catwalk, or raised platform view.
7. First-person weapon idle view with HUD.
8. First-person weapon firing view with muzzle/feedback.
9. Low-poly opposing player character.
10. Death/respawn state screen.
11. Two-player multiplayer combat view.

Reference image art direction:
The images should show:
- Low-poly angular geometry.
- Dusty industrial/desert compound atmosphere.
- Muted beige, tan, gray, olive, rust, brown, faded blue, and dark green palette.
- Concrete/plaster buildings.
- Crate stacks.
- Narrow alleys.
- Metal shutters or doors.
- Central courtyard.
- Underpass or covered passage.
- Raised balcony or catwalk.
- Retro tactical HUD.
- First-person low-poly weapon.
- Boxy humanoid player characters.
- Old-PC/mod-like visual roughness.

The images should not show:
- Any actual Counter-Strike map layout.
- Counter-Strike logos, names, weapons, characters, textures, or UI.
- Photorealistic AAA visuals.
- Modern military shooter style.
- Glossy sci-fi environments.
- Minecraft-like voxel visuals.
- Mobile-game/cartoon visuals.
- SaaS-like UI.

If image generation is not available in the implementation environment:
- Create the reference-image prompts anyway.
- Use any provided reference image as the visual target.
- Do not skip the visual-target step.
- Summarize the intended look before coding.

After generating or receiving the references, inspect them and write a visual target summary covering:
1. Color palette.
2. Map atmosphere.
3. Geometry style.
4. HUD/menu style.
5. Character style.
6. Weapon style.
7. Lighting style.
8. What must be avoided.

Then implement the browser game so the rendered result approximates those references.

Visual target:
The accepted visual style is an original browser-native homage to early-2000s tactical shooters.

The visual style should be:
- Low-poly.
- Angular.
- Slightly gritty.
- Muted.
- Readable.
- Lightweight.
- Old-PC/mod-like.
- Functional rather than cinematic.

The game should look closer to an early tactical FPS mod than to:
- A modern web demo.
- A SaaS dashboard.
- A sci-fi arena.
- A Minecraft-like voxel scene.
- A mobile shooter.
- A glossy modern AAA shooter.

Environment visual direction:
Use simple geometric architecture and materials that suggest:
- Concrete.
- Plaster.
- Sand.
- Asphalt.
- Metal.
- Wood.
- Crates.
- Worn industrial surfaces.
- Dusty exterior areas.
- Narrow interior passages.

Use a muted palette:
- Beige.
- Tan.
- Dust brown.
- Concrete gray.
- Olive.
- Rust.
- Faded blue.
- Dark green.
- Charcoal.

Acceptable visual treatment:
- Flat-shaded or lightly shaded geometry.
- Low-resolution or procedural material feel.
- Strong silhouettes.
- Simple lighting.
- Sparse shadows or contrast where useful.
- Abstract original signage or markings.
- Old-game-like roughness and material variation.

Avoid:
- Photorealism.
- Glossy PBR-heavy presentation.
- Heavy bloom.
- Cinematic post-processing.
- Smooth futuristic architecture.
- Cartoon/mobile-game styling.
- Direct Counter-Strike textures, logos, props, map names, or map layouts.

Optional open-source / free asset research phase:
Before building final environment props, character placeholders, textures, or decorative models, research whether suitable open-source, public-domain, CC0, permissively licensed, or otherwise free-to-use 3D assets exist.

This phase is optional. Do not use external assets just for the sake of using them. Use external assets only if they improve the visual target, preserve browser performance, and have a clearly usable license.

Preferred asset strategy:
1. Prefer original procedural geometry and simple low-poly shapes when they are sufficient.
2. Use external free/open assets only for things that benefit from extra detail, such as crates, doors, shutters, barrels, industrial props, wall materials, ground materials, simple humanoid placeholders, environmental details, and ambience.
3. Keep all assets visually consistent with the generated reference images and the early-2000s tactical FPS style.
4. Do not mix visually incompatible asset packs.
5. Avoid high-poly, photorealistic, glossy, modern military, sci-fi, fantasy, cartoon, or mobile-game-like assets.
6. Do not use any Counter-Strike assets, extracted game files, copied textures, copied map geometry, copied character models, copied UI, copied logos, or copied sounds.
7. For the first-person prop, prefer an original abstract low-poly model created from simple geometry rather than sourcing a real-world firearm model.

Acceptable asset licenses:
Only use assets when the license is clearly compatible with this project.

Preferred:
- CC0 / public domain.
- MIT.
- Apache-2.0.
- BSD-style licenses.
- Other clearly permissive licenses.

Allowed with caution:
- CC BY, only if attribution is practical and added to the README or credits.
- Store/free licenses only if the terms clearly allow use in an interactive browser game and derivative works.

Avoid unless explicitly justified:
- CC BY-SA, because share-alike obligations may complicate the project.
- Custom licenses with unclear terms.
- Assets from aggregators where the original author/license cannot be verified.

Do not use:
- CC BY-NC or any NonCommercial license.
- CC BY-ND or any NoDerivatives license.
- Editorial-use-only assets.
- Ripped game assets.
- Assets whose source, author, or license cannot be verified.
- Assets that require attribution but do not provide enough attribution information.
- Any asset that resembles a direct Counter-Strike asset replacement.

Suggested asset research targets:
Look for lightweight low-poly assets that fit these categories:
1. Industrial crates and pallets.
2. Concrete barriers and low walls.
3. Metal shutters and doors.
4. Corrugated panels.
5. Simple barrels or containers.
6. Low-poly building pieces.
7. Simple ground/concrete/plaster textures.
8. Dusty industrial props.
9. Low-poly humanoid placeholders.
10. Ambient environment pieces such as lamps, vents, pipes, signs, and railings.

Asset-source verification:
For every external asset considered, verify:
1. Original source page.
2. Author or publisher.
3. Exact license.
4. Whether commercial use is allowed.
5. Whether modification/derivative use is allowed.
6. Whether attribution is required.
7. Whether redistribution inside this project is allowed.
8. Whether the asset visually fits the reference images.
9. Whether the asset is lightweight enough for browser use.

Asset manifest:
If any external asset is used, create or update an asset manifest in the README or a dedicated credits file.

For each asset, record:
- Asset name.
- Author/publisher.
- Source page.
- License.
- Whether attribution is required.
- Where it is used in the project.
- Any modifications made.
- Date checked.

External asset acceptance gate:
An external asset may be used only if:
1. The license is clearly acceptable.
2. The asset is original/free/open, not copied from Counter-Strike or another commercial game.
3. The asset fits the generated visual references.
4. The asset does not make the game look modern, photorealistic, sci-fi, cartoonish, or inconsistent.
5. The asset does not significantly harm browser performance.
6. Attribution, if required, is included.

External asset rejection gate:
Reject the asset if:
1. The license is missing, unclear, restrictive, NonCommercial, or NoDerivatives.
2. The source appears to be a ripped game asset.
3. The asset resembles Counter-Strike content too closely.
4. The asset breaks the visual style.
5. The asset is too high-poly or heavy for a browser prototype.
6. The asset introduces unnecessary complexity.
7. The same effect can be achieved more cleanly with simple original geometry.

Visual consistency rule:
External assets must serve the generated reference images, not override them. If an imported model makes the scene less coherent, more modern, too realistic, or less like an early-2000s tactical FPS homage, remove it and replace it with simpler original geometry.

Main map direction:
The main map should be an original dusty industrial/desert compound that strongly evokes the early-2000s tactical FPS era without copying any real Counter-Strike map.

It should feel like:
- A sun-baked exterior yard.
- Squared concrete or plaster buildings.
- Narrow alleys.
- Crate stacks.
- Metal shutters or doors.
- A small underpass, tunnel, or covered passage.
- A raised balcony, catwalk, ledge, or platform.
- A central contested courtyard.
- A mix of exterior and interior spaces.
- A compact tactical layout with lanes, cover, corners, and recognizable callout-style landmarks.

It should not feel like:
- A literal de_dust, de_dust2, cs_assault, cs_office, or other Counter-Strike map.
- A random pile of boxes.
- A single empty room.
- A maze.
- A clean esports aim-training grid.
- A modern military shooter map.
- A sci-fi arena.
- A Minecraft-like voxel map.

Good map criteria:
A good map is not just a collection of walls and boxes. It should feel like a compact tactical FPS space with readable flow, intentional routes, tactical choices, and memorable landmarks.

The main map is accepted only if it satisfies these criteria:

1. Clear tactical structure
- The map has two opposing spawn areas.
- The spawn areas are visually distinct.
- Players can understand the general direction of conflict within a few seconds.
- The layout naturally pulls players toward a central contested area.
- The map supports quick engagements without feeling cramped.

2. Multiple viable routes
The map must have at least three meaningful routes between the two sides:
- A main central lane with medium-to-long sightlines.
- A tighter interior or corridor route with closer engagements.
- A flank route that allows repositioning and surprise angles.

These routes should reconnect in sensible places. They should not feel like isolated hallways.

3. Choke points and rotations
- The map should have choke points where encounters naturally happen.
- Choke points should have nearby cover or alternate exits.
- Players should be able to rotate from one route to another.
- Rotations should create tactical choices, not just linear movement.

4. Sightline quality
- Include a few longer sightlines for tactical tension.
- Break up overly long sightlines with corners, crates, walls, pillars, elevation changes, or doorways.
- Avoid letting players see the whole map from one position.
- Avoid random clutter that makes aiming or navigation confusing.

5. Cover placement
Cover should feel purposeful.

Use:
- Low walls.
- Crates.
- Pillars.
- Door frames.
- Ramps.
- Corners.
- Partial-height structures.

Cover should create tactical decisions:
- Peek.
- Cross.
- Hold.
- Retreat.
- Flank.

Avoid huge empty areas with no cover. Avoid cover that blocks movement awkwardly or creates frustrating dead ends.

6. Landmarks and orientation
Players should be able to mentally call out areas even without labels.

The map should include at least 4 recognizable landmarks, such as:
- Central yard.
- Warehouse entrance.
- Crate stack.
- Underpass.
- Raised balcony.
- Metal gate.
- Broken wall.
- Loading bay.
- Narrow alley.
- Rooftop ledge.
- Interior storage room.
- Long corridor.
- Courtyard stairs.

A player should be able to say things like:
- “I am near the crate stack.”
- “I am entering the underpass.”
- “I am holding the balcony.”
- “I am crossing the central yard.”

7. Verticality
The map should include limited, readable verticality.

Acceptable examples:
- A raised platform.
- A balcony.
- A ramp.
- A short staircase.
- A window-like overlook.
- A rooftop edge.
- A catwalk.

Do not overdo verticality. This should still feel like an early tactical FPS map, not a parkour arena.

8. Spawn quality
- Spawns should not immediately expose players to direct fire.
- Players should have at least two route choices shortly after spawning.
- Players should reach possible combat within a few seconds.
- Spawn areas should not be confusing or oversized.

9. Scale and pacing
The map should be compact.
- Players should encounter action quickly.
- Routes should be long enough to create tactical movement.
- The map should not feel like a maze.
- The map should not feel like a single room.
- The player should be able to learn the layout after a few minutes.

10. Visual readability
- Walkable areas, walls, cover, doors, ramps, and elevated positions should be visually clear.
- Player silhouettes should stand out against the environment.
- Lighting should help orientation.
- Decorative elements should not interfere with combat readability.

11. Originality
The map must not copy de_dust, de_dust2, cs_assault, cs_office, or any other Counter-Strike map.

It can evoke the same era and tactical design language, but the layout, landmarks, names, materials, and flow must be original.

Additional maps:
Include at least 5 original maps or map entries total. They can share the same rendering style, but each should have a distinct identity.

Suggested themes:
1. Dusty industrial compound.
2. Warehouse depot.
3. Concrete bunker.
4. Dockyard or shipping yard.
5. Office block or storage facility.
6. Refinery yard.
7. Train-adjacent industrial lot.

Each map should have:
- A name.
- A short description.
- A visual theme.
- Spawn areas.
- Cover.
- Choke points.
- At least one distinctive landmark.
- A preview or clear representation in the map-select screen.

Gameplay requirements:
Implement a lightweight deathmatch-style prototype.

Required mechanics:
1. First-person camera.
2. Mouse look.
3. Pointer-lock style FPS control or equivalent browser FPS control.
4. Keyboard movement.
5. Collision against major map geometry.
6. Crosshair.
7. First-person weapon visible on screen.
8. Shooting.
9. Hit detection.
10. Player HP.
11. Death state.
12. Respawn.
13. Shot feedback.
14. Hit feedback.
15. Death or respawn feedback.
16. Map selection.
17. Multiplayer presence.
18. Multiplayer shooting.
19. Player count or player list.
20. Return to map selection.

Do not implement unnecessary scope such as:
- Economy.
- Weapon buying.
- Bomb objectives.
- Hostage objectives.
- Matchmaking.
- Accounts.
- Ranking.
- Inventory systems.
- Realistic ballistics.
- Complex weapon loadouts.
- Destructible environments.
- Advanced AI.

The target loop is:
Join a map → move around → see other players → shoot → take damage → die → respawn → continue playing.

Movement feel:
Accepted:
- Responsive movement.
- Stable camera.
- Clear collision.
- Movement speed appropriate for a compact tactical FPS.
- Optional sprint/walk behavior if it improves feel.
- No major clipping through walls.
- No excessive sliding, floating, or bouncing.

Not accepted:
- Movement that feels uncontrollable.
- Camera jitter.
- Falling through the map.
- Walking through major walls.
- Getting stuck frequently.
- Movement so fast that the map becomes unreadable.

Shooting feel:
Accepted:
- Simple hitscan shooting.
- Crosshair-aligned shots.
- Immediate shot feedback.
- Small weapon recoil animation.
- Firing sound.
- Hit confirmation.
- HP reduction.
- Death and respawn.

Not accepted:
- Shots that do not align with the crosshair.
- No visible or audible firing feedback.
- Damage that is inconsistent across clients.
- Shooting that crashes or desynchronizes the game.
- Overcomplicated ballistics that make the prototype unreliable.

Player/character visuals:
Other players should look like simple low-poly tactical characters. They should not be realistic soldiers and should not copy Counter-Strike models.

Accepted:
- Boxy low-poly humanoids.
- Clear head, torso, arms, legs, and weapon shape.
- Distinct team colors or markings.
- Readable facing direction.
- Simple movement bob or pose change.
- Clear alive/dead state.

Not accepted:
- Realistic soldier models.
- Imported copyrighted character models.
- Overly detailed modern tactical gear.
- Characters that are just anonymous cubes with no readable humanoid form.

First-person weapon:
The local player should see a simple original low-poly weapon in the lower part of the screen.

Accepted:
- Simple original low-poly weapon shape.
- Stable position relative to the camera.
- Slight walking motion.
- Small firing animation or recoil.
- Visual alignment with the crosshair.
- Clear return to resting position after firing.

Not accepted:
- Copying a Counter-Strike weapon model.
- A weapon that floats away from the camera.
- A weapon that rotates incorrectly or detaches.
- A weapon that obscures too much of the screen.
- No visible weapon.

HUD and menu:
The UI should feel like an early tactical shooter interface.

Include:
- Health.
- Ammo or firing status.
- Current map name.
- Player count.
- Crosshair.
- Hit indicator.
- Death/respawn status.
- Basic scoreboard or player list.
- Map-selection screen.

Accepted visual treatment:
- Dark translucent panels.
- Thin borders.
- Compact text.
- Muted colors.
- Angular layout.
- Slightly pixelated or old-PC feel where practical.
- Map list with previews.
- Functional tactical game UI.

Not accepted:
- Generic landing-page UI.
- Modern SaaS dashboard styling.
- Mobile-game UI.
- Large glossy buttons.
- Overdesigned cinematic menus.

Audio:
Use original lightweight browser-generated or procedural sounds. Do not use copyrighted sound effects.

Include:
- Firing sound.
- Hit confirmation sound.
- Death or respawn cue.
- Optional menu sounds.

The sounds should be simple, compressed, synthetic, and retro.

Multiplayer requirements:
1. Players in the same map should see each other.
2. Player position and facing direction should update across clients.
3. Player alive/dead state should be visible across clients.
4. Shooting should be shared across clients.
5. Taking damage, death, and respawn should work consistently enough for a prototype.
6. Different maps should behave as different rooms.
7. Users joining and leaving should not break the session.
8. The app should display the number of connected players or a simple player list.
9. If multiplayer configuration is unavailable, the app should fall back gracefully to local play or provide a clear message.

Technical direction:
Use the existing project stack where practical. Choose simple, browser-native technologies appropriate for a 3D web game.

Do not over-prescribe architecture. The implementation should be clean, maintainable, and understandable, but the exact file structure and libraries are up to the implementation.

Technical expectations:
1. The app should build successfully.
2. The app should run locally with documented commands.
3. Rendering, input, gameplay, map data, UI, and multiplayer logic should be reasonably separated.
4. Avoid one giant unmaintainable file if possible.
5. Avoid unnecessary dependencies.
6. Keep performance acceptable on a normal laptop.
7. Handle errors gracefully.
8. Update documentation with setup, testing, limitations, asset usage, and verification results.

If a realtime/backend service already exists in the project, use it.

If no backend exists and external setup is impractical, provide:
- Local playable mode.
- Clear multiplayer configuration instructions.
- A graceful fallback when multiplayer is unavailable.

Map selection requirements:
The front page should feel like an old tactical shooter map/server selection screen.

It should include:
- Available maps.
- Map names.
- Short descriptions.
- Visual themes.
- Player count if available.
- Join button or equivalent action.
- Preview or visual representation for each map.

The selected map should determine the multiplayer room/session.

Quality bar:
This should feel like a coherent mini-game, not just a technical proof of concept.

Prioritize:
1. Playability.
2. Visual coherence.
3. Stable browser performance.
4. Readable map layout.
5. Multiplayer clarity.
6. Old-school tactical FPS atmosphere.
7. Evidence-based visual verification.

Implementation sequence:
1. Inspect the existing repo and identify the app stack, package manager, and any available realtime/backend setup.
2. Generate or prepare the visual reference-image set.
3. Write the visual target summary from the reference images.
4. Research optional free/open 3D assets if they could materially improve the result.
5. Verify licenses for any external assets before using them.
6. Build the local single-player loop first:
   menu, map select, map scene, movement, collision, weapon, shooting, HUD, HP, death, and respawn.
7. Design the main map around the good-map criteria:
   spawns, three routes, central contested area, cover, landmarks, verticality, and readable sightlines.
8. Add at least 5 original map entries.
9. Add simple low-poly player models.
10. Add retro HUD/menu treatment.
11. Add original lightweight audio feedback.
12. Add multiplayer presence.
13. Add multiplayer shooting, damage, death, and respawn.
14. Verify two-tab multiplayer.
15. Run build/lint/type checks.
16. Capture actual browser screenshots.
17. Compare actual screenshots against the generated references.
18. Perform visual style, feel, multiplayer, and map-readability verification.
19. Fix any failures.
20. Update README and asset manifest/credits if external assets were used.
21. Provide a final implementation report.

Verifier gates:
Run and satisfy these gates before declaring the task complete.

Gate 1 — Build:
- Dependencies install successfully.
- Type checking passes if configured.
- Linting passes if configured.
- Production build succeeds.

Gate 2 — Browser launch:
- The app launches locally.
- The menu appears.
- The map-selection screen works.
- A player can join a map.
- The game scene loads without blocking console errors.

Gate 3 — Visual target:
- The game clearly evokes an original early-2000s tactical FPS aesthetic.
- The map is low-poly, angular, muted, and readable.
- The HUD and menus feel retro rather than modern SaaS.
- No copyrighted Counter-Strike assets, names, logos, sounds, or copied map layouts are present.

Gate 4 — Map quality:
- The main map has two spawn areas.
- The main map has a central contested zone.
- The main map has at least three meaningful routes.
- The main map has cover, corners, choke points, and sightlines.
- The main map has at least one elevated or semi-elevated position.
- The main map has recognizable landmarks.
- The main map supports quick engagements after spawning.
- The main map does not copy any real Counter-Strike map.

Gate 5 — Core gameplay:
- Movement works.
- Mouse look works.
- Collision works against major geometry.
- Crosshair is visible.
- First-person weapon is visible.
- Shooting works.
- Hit detection works.
- HP, death, and respawn work.
- Player can return to map select.

Gate 6 — Weapon and feedback:
- Weapon stays attached to the camera.
- Weapon firing animation works.
- Shot sound plays.
- Hit feedback appears.
- Death or respawn feedback appears.

Gate 7 — Multiplayer:
Using two browser tabs or windows:
- Both clients can join the same map.
- Each client sees the other player.
- Movement updates across clients.
- Facing direction is understandable.
- Shooting is shared across clients.
- Damage, death, and respawn are reflected across clients.
- Player count or player list updates.
- Different maps behave as separate rooms.

Gate 8 — Map selection:
- At least 5 original maps or map entries exist.
- Each has a name, description, theme, spawn setup, cover, and landmark.
- The map-selection screen shows the available maps.
- Selecting a map joins the correct room/session.

Gate 9 — Error handling:
- Missing multiplayer configuration does not crash the app.
- Disconnects do not crash the app.
- Respawning does not crash the app.
- Changing maps does not duplicate old scenes or stale players.
- Normal gameplay does not produce recurring console errors.

Gate 10 — Asset licensing:
If external assets are used:
- Every asset has a verified source.
- Every asset has a compatible license.
- Attribution is included where required.
- Asset usage is documented.
- No ripped or copyrighted commercial game assets are used.
- No Counter-Strike assets are used.

If no external assets are used:
- State that the implementation uses original procedural/simple geometry.
- Explain why external assets were unnecessary.

Gate 11 — Documentation:
Update the README with:
- What was built.
- How to run locally.
- How to test multiplayer.
- How maps work.
- How the visual reference process worked.
- External assets used, if any.
- Known limitations.
- Commands run.
- Which verifier gates passed or failed.

Visual style and feel verification:
Do not rely only on “it builds” or “the 3D scene renders.” The project must prove that it visually and mechanically feels like an original early-2000s tactical FPS prototype.

Required visual evidence:
Capture or inspect the following views from the actual browser game:

1. Main menu / map-selection screen.
2. Spawn view on the main map.
3. Central contested area.
4. Narrow corridor or interior route.
5. Flank route.
6. Elevated or semi-elevated position.
7. First-person weapon view while idle.
8. First-person weapon view while firing.
9. View of another player character.
10. Death or respawn state.
11. Two-player multiplayer view, using two browser tabs if possible.

These views should make the intended style obvious without reading the code.

Reference-to-implementation comparison:
After implementation, capture screenshots from the actual browser game and compare them against the generated references.

Compare:
1. Menu reference vs actual menu.
2. Map-select reference vs actual map-select screen.
3. Spawn-view reference vs actual spawn view.
4. Central courtyard reference vs actual central area.
5. Corridor reference vs actual corridor.
6. Flank reference vs actual flank route.
7. Weapon/HUD reference vs actual weapon/HUD.
8. Character reference vs actual player model.
9. Death/respawn reference vs actual death/respawn state.
10. Multiplayer reference vs actual two-tab multiplayer view.

Score each comparison from 0 to 3:
0 = does not match the reference direction.
1 = weak match.
2 = acceptable match.
3 = strong match.

Passing threshold:
- Average score must be at least 2.2.
- No critical category may score 0.
- Menu/HUD, main map atmosphere, player character readability, first-person weapon, and tactical map readability must each score at least 2.

Critical reference-match failures:
The implementation fails the visual target if:
1. The actual game looks like generic gray boxes despite the reference images being richer.
2. The menu/HUD does not resemble the generated retro tactical UI direction.
3. The map loses the dusty industrial/desert compound atmosphere.
4. The actual map does not contain readable landmarks, routes, cover, and sightlines.
5. The first-person weapon is missing or visually incoherent.
6. Other players are not recognizable as low-poly humanoid characters.
7. The implemented result looks like a modern SaaS demo, sci-fi arena, Minecraft-like scene, or generic browser 3D playground.

Visual style self-test:
Look at the captured or inspected views and answer these questions honestly:

1. If someone saw this for 5 seconds, would they understand it is a retro tactical FPS?
2. Does it look closer to an early Counter-Strike-era mod than to a modern web demo?
3. Does the environment feel like a believable compact tactical map rather than random boxes?
4. Are there recognizable lanes, corridors, cover pieces, and landmarks?
5. Is the color palette muted, dusty, industrial, and old-game-like?
6. Are the shapes angular and low-poly?
7. Are the HUD and menus game-like rather than SaaS-like?
8. Are characters recognizable as low-poly humanoid combatants?
9. Is the first-person weapon visible, stable, and visually coherent?
10. Does the map feel original rather than copied from Counter-Strike?

Accepted answer:
Most answers should be clearly “yes.”

If the answer to questions 1, 2, 3, 4, 8, or 9 is “no,” the visual style is not accepted yet.

Visual scoring rubric:
Score the result from 0 to 3 on each category.

0 = absent or wrong.
1 = present but weak.
2 = acceptable.
3 = strong.

Categories:
1. Retro tactical FPS identity.
2. Low-poly early-2000s feel.
3. Dusty/industrial/desert compound atmosphere.
4. Map readability.
5. Meaningful cover and sightlines.
6. Recognizable landmarks.
7. Originality of layout and assets.
8. HUD/menu style.
9. Character readability.
10. First-person weapon presentation.
11. Lighting and material coherence.
12. Overall browser-game polish.

Passing threshold:
- Total score must be at least 27 out of 36.
- No category may score 0.
- Retro tactical FPS identity, map readability, originality, character readability, and first-person weapon presentation must each score at least 2.

Critical visual fail conditions:
The visual style fails automatically if any of these are true:

1. The map looks like random gray boxes.
2. The game looks like a generic Three.js or browser 3D demo.
3. The UI looks like a modern SaaS dashboard.
4. The scene looks sci-fi, fantasy, Minecraft-like, or mobile-cartoon-like.
5. There is no clear tactical map structure.
6. There are no recognizable landmarks.
7. Player characters are not readable as humanoids.
8. There is no visible first-person weapon.
9. The weapon floats away, clips badly, or feels detached from the camera.
10. The layout copies an actual Counter-Strike map.
11. Any copyrighted Counter-Strike assets, names, textures, sounds, logos, or map layouts are used.

Feel verification:
Run a short 60-second playtest on the main map.

During the playtest, verify:

1. Within 5 seconds, the player understands they are in a tactical FPS map.
2. Within 10 seconds, the player can identify at least two possible routes.
3. Within 15 seconds, the player reaches a meaningful combat area.
4. Movement feels responsive and not slippery, floaty, or uncontrollable.
5. The player can use cover naturally.
6. The crosshair, weapon, and shot direction feel aligned.
7. Firing gives immediate visual and audio feedback.
8. Getting hit, dying, and respawning are understandable.
9. The map feels compact but not like a single room.
10. The player can mentally name at least four areas or landmarks after exploring.

Passing threshold:
The feel test passes only if at least 8 of the 10 checks are true.

Two-tab multiplayer feel test:
Open the game in two browser tabs or windows and join the same map.

Verify:
1. Both players appear in the same environment.
2. The other player’s movement is readable.
3. The other player’s facing direction is understandable.
4. Shooting at the other player feels plausible.
5. Damage, death, and respawn are reflected clearly enough.
6. The experience still feels like a tactical FPS, not just two cubes moving around.

Passing threshold:
All six checks must pass for multiplayer feel to be accepted.

Map readability test:
Without looking at the map data or code, inspect the main map in-game and identify:

1. The two spawn areas.
2. The central contested area.
3. The main lane.
4. The corridor/interior route.
5. The flank route.
6. At least four landmarks.
7. At least three meaningful cover positions.
8. At least one elevated or semi-elevated position.

Passing threshold:
At least 7 of these 8 items must be clearly identifiable from gameplay.

Visual QA report:
Before finishing, create or update a short visual QA section in the final response or README.

Include:
1. Reference images generated or used.
2. Visual target summary derived from the references.
3. Screens/views reviewed from the actual browser game.
4. Reference-to-implementation comparison scores.
5. Visual rubric score.
6. Feel test result.
7. Multiplayer feel test result.
8. Map readability result.
9. Any visual weaknesses that remain.
10. Specific changes made to improve style or feel.

Final completion rule:
Do not claim the visual target is complete unless:
1. The visual reference phase was completed.
2. The final browser screenshots are acceptably close to the generated reference images.
3. The visual scoring rubric passes.
4. The critical visual fail conditions are all avoided.
5. The 60-second feel test passes.
6. The two-tab multiplayer feel test passes.
7. The map readability test passes.
8. The final result visibly reads as an original early-2000s tactical FPS homage, not merely a functional browser shooter.

Acceptance criteria:
The task is complete only when:

1. The app builds successfully.
2. The app runs fully in the browser.
3. The user can select a map and play.
4. The game visibly evokes early-2000s tactical FPS aesthetics while remaining original.
5. The main map has a clear tactical layout with lanes, cover, landmarks, spawn areas, and a central contested zone.
6. Movement, camera, collision, shooting, HP, death, and respawn work.
7. The first-person weapon and HUD work.
8. At least 5 original maps or map entries are available.
9. Multiplayer presence works in two browser tabs.
10. Multiplayer shooting works in two browser tabs.
11. The app handles missing multiplayer configuration gracefully.
12. External assets, if any, are license-verified and documented.
13. The README explains setup, testing, map design, multiplayer behavior, asset usage, visual QA, and limitations.
14. No copyrighted Counter-Strike assets, exact map copies, logos, names, sounds, models, textures, or layouts are used.

Final response format:
When done, respond with:

1. What was implemented.
2. Reference images generated or used.
3. Visual target summary.
4. How the main map was designed.
5. How the accepted visual style was achieved.
6. How the accepted mechanics were achieved.
7. External assets used, if any, with license notes.
8. Files changed.
9. Commands run and results.
10. Verifier gates passed or failed.
11. Reference-to-implementation comparison score.
12. Visual rubric score.
13. Feel test result.
14. Two-tab multiplayer test result.
15. Map readability test result.
16. Known limitations.
17. How to run and test locally.
