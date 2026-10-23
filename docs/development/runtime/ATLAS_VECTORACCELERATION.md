# set_projectile_vector_acceleration

Timed signed two-axis world acceleration, independent of the selected trajectory. Adds the authored vector after movement, turn and multiplicative speed, before absolute speed ramp and homing; zero axes are explicit. The compiler divides acceleration by the square of updatesPerTick so the same world-time phase gives the same world velocity change. It can launch a stationary zero-velocity projectile without inventing a direction.

The capability registry owns all required fields and world-unit projections. The compiler uses the generic modifier projection with one receipt per field; Author, Repair and wire schemas derive from the same registry. Native phase clock uses active age, excluding activation delay. Late hydration retains that clock. GPU/world/multiplayer-session validation: notRun.
