# Delivery patterns: slices, strangler fig, branch by abstraction, toggles

Read this when a decision is about how to structure features, migrate a legacy part, or roll out a big change in small steps.

## Vertical slices vs horizontal layers

Horizontal layers (controllers/, services/, repositories/) group by technical role, so one feature touches many folders. Vertical slices group by business capability: each slice holds its request, validation, logic and data access, and shares only the domain kernel and ports (Jimmy Bogard, "Vertical Slice Architecture", blog, 2018).

When it helps: many independent features, parallel agents or teams, features that change for different reasons.
When it hurts: heavy shared business rules (risk of copying rules into each slice; keep shared rules in the domain kernel), very small apps.

Agent angle: a slice bounds what an agent must read and gives each agent a disjoint set of files to own.

## Strangler fig

Put a routing facade in front of the old part, build new behaviour beside it, move routes over one by one, then delete the old part (Fowler, "StranglerFigApplication", 2004). Use for replacing a subsystem without a big-bang rewrite.

## Branch by abstraction

Add an interface over the part you will replace, move callers to the interface, build the new implementation behind it, switch by configuration, delete the old one; all on main in small commits (Paul Hammant, 2007; Fowler, "BranchByAbstraction", 2014). Use instead of long-lived branches.

## Release toggles

Separate deploy from release with short-lived toggles. Every toggle has an owner and a removal date; a CI check fails on expired toggles (Pete Hodgson, "Feature Toggles", martinfowler.com, 2017). Red flag: toggles with no removal date, or toggles used as permanent configuration.

## Small batches

Small batch size is one of the capabilities linked to better delivery performance (Forsgren, Humble & Kim, *Accelerate*, 2018). Big refactors go through the patterns above as a series of small, separately mergeable PRs.
