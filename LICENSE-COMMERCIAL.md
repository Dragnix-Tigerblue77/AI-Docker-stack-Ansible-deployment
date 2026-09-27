<!--
SPDX-FileCopyrightText: 2026 Tigerblue77
SPDX-License-Identifier: AGPL-3.0-only
-->

# Commercial licence

This project is dual-licensed. It is available:

- to everyone, under the [GNU Affero General Public License version 3](./LICENSE) (`AGPL-3.0-only`), at no cost and with no formality;
- or, to those who ask for it, under a **separate commercial licence** negotiated with the copyright holder, Tigerblue77 ([@tigerblue77](https://github.com/tigerblue77)), who holds — or, for contributed work, is granted under [`CONTRIBUTING.md`](./CONTRIBUTING.md) — the right to offer every line here under both arms.

**The two are alternatives, and which one you rely on is yours to choose — with one asymmetry worth naming up front.** The AGPL arm is open to everyone without asking anybody: nothing here restricts that grant, taking this work under the AGPL requires no permission, no registration and no notice to anyone, and this page cannot and does not add conditions to it. The commercial arm exists only by agreement with the copyright holder, and this page is where you ask for it. If the AGPL suits you — and for anyone deploying this stack on their own machines, it does — you need nothing from this page.

## Do I need one ?

Almost certainly not. This repository holds one Ansible role: it renders the Artificial Intelligence stack's compose file and hands it to a deployment role the caller names. It is material you *run* against machines you point it at.

Running it is not conveying it, and the AGPL's reciprocal obligations attach to conveying — with the one exception the table below relies on: section 13 attaches to a **modified** version that users drive over a network, whether or not you ever convey it.

| What you are doing | AGPL is enough | Commercial licence |
|---|:---:|:---:|
| Running the role against your own machines, at home | ✅ | |
| Running it against your employer's machines, in production, at any scale | ✅ | |
| Copying the role into your own private Ansible repository and never publishing it | ✅ | |
| Adding your own services to the stack and keeping the result to yourself | ✅ | |
| Publishing your modified role, under the AGPL | ✅ | |
| Redistributing it as-is, licence and notices intact | ✅ | |
| Deploying the rendered stack onto a client's machine, licence and notices intact, corresponding source available on request | ✅ | |
| Shipping this role inside a commercial provisioning or AI product and **not** releasing your modified source under the AGPL | | ✅ |
| Bundling it into a proprietary automation or MSP platform whose source you cannot publish | | ✅ |
| Running a hosted service built on a **modified** version of this role, whose users drive it remotely, while declining the section 13 source obligation | | ✅ |
| Wanting a warranty, an indemnity or a support commitment from the copyright holder | | ✅ |

That last row is a contract you are buying, not a permission you lack. The AGPL offers none of the three — it disclaims warranty (section 15) and limits liability (section 16) — but it does not stand in the way of one either: section 4 lets anyone offer support or warranty protection for a fee, from the copyright holder or from anybody else.

The short version: **using** it never requires a commercial licence, with the single exception of section 13 above, where a modified version is driven remotely by its own users. Otherwise only **conveying** it while withholding the corresponding source does, and that is exactly what the AGPL asks in exchange for the grant.

Three consequences are worth spelling out, because they are what enquiries about Ansible content usually turn out to be about.

- **Copyleft reaches this role, not the software the stack deploys.** `services:` is an empty mapping today, and every image a service issue adds to it — an LLM gateway, a vector database, a reranker, the agents and connectors around them — keeps its own licence entirely. None of them is derived from this role, and this repository neither contains nor distributes any of them: it names them, and your own container runtime fetches them from their own registries. [`NOTICE`](./NOTICE) records that.
- **It does not reach your inventory, your variables, your FQDNs or your secrets.** Those are your data, written by you, describing your estate — copyleft follows the code you received and modified, not what you feed it.
- **Section 13 concerns a modified version whose users drive it over a network.** A playbook run from an operator's workstation exposes no network interface to anybody, and an unmodified version triggers nothing at all, so section 13 stays dormant in ordinary use. The web interfaces the stack will eventually publish belong to the programs behind them, under their own licences, not to this one; section 13 here matters only if you have modified the role and built a service around it that *its users* drive remotely.

One case deserves naming rather than leaving to be discovered, because it is the likeliest enquiry about a role like this one: rendering the stack onto a machine that is not yours. Landing the rendered compose file on a host you control is running the work. Landing it on a client's host hands a third party a copy of a work derived from this template — the AGPL permits that too, provided the copy carries the licence and the notices and you can supply the corresponding source (sections 4 and 5). It is the withholding, not the deployment, that needs the other arm.

## What the commercial licence typically covers

Terms are agreed case by case. The shape on offer is:

- a non-exclusive right to use, modify and redistribute the work in source or derived form, **without** the AGPL's reciprocal source-disclosure obligations;
- the right to sublicense it as part of a larger product, under the licensee's own terms;
- the attribution and notice obligations reduced to what the licensee's product can practically carry;
- optionally: a warranty, an indemnity, a support or maintenance commitment — none of which the AGPL version carries.

It covers only the parts whose copyright this project holds or is authorised to sublicense. Today that excludes nothing: the tree is the copyright holder's own work. It is not expected to stay that way — this repository is shared, and [`CONTRIBUTING.md`](./CONTRIBUTING.md) is what keeps a future contribution offerable under both arms instead of under the AGPL alone, which is why it was written before the first outside contribution rather than after it.

It does not and cannot cover the container images the stack will name: those are third-party works your own runtime fetches from their own registries, and they keep their own terms in every case. This repository contains none of them and distributes none of them — [`NOTICE`](./NOTICE) is where that is recorded, and where an image whose own terms require a notice to travel alongside would be named.

## How to ask

**Through GitHub.** Open an issue on this repository describing your use case, or reach the copyright holder, [@tigerblue77](https://github.com/tigerblue77), on his profile there. An issue is the better of the two unless what you have to say is confidential: it is seen sooner, and it leaves a record both sides can point back to — but while this repository stays private an outsider cannot open one at all, so until it is public the profile is the route.

Please include:

1. what the product or service is, and how this role would sit inside it;
2. whether you would redistribute it, host it, or both;
3. the scale involved, and the obligations you specifically need lifted;
4. any warranty, indemnity or support requirement.

There is no published price list, because there is no standard case. Small-volume, hobbyist and non-profit uses that genuinely cannot fit the AGPL are the cases this arm exists to settle for nothing at all — ask.

## Notes

- **This page is not itself a licence.** It is a description of an offer to negotiate. A commercial licence exists only once it is signed; until then, the AGPL is the only licence in force, and it applies in full.
- **Contributors:** [`CONTRIBUTING.md`](./CONTRIBUTING.md) explains why contributing here means granting the copyright holder the right to include your contribution under both arms of the licence, and what that does and does not mean for you — in particular that every copy already released under the AGPL stays released under it, since a grant made on a copy cannot be withdrawn from whoever holds it.
- **No licence history.** This repository has carried the AGPL since its first commit; there is no earlier set of terms, nothing was relicensed, and nothing was withdrawn from anyone. [`NOTICE`](./NOTICE) records it, so that a reader who expects to find a chain here knows there is none to find.
