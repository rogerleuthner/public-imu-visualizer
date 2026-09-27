// Copyright © 2026 Roger B. Leuthner. All rights reserved.  This software is provided for informational and educational purposes. Use of this software does not imply endorsement by the author of any particular use or application. The author assumes no responsibility or liability for any damages or consequences arising from its use.

import { rm } from "node:fs/promises";

await rm("dist", { recursive: true, force: true });
await rm("../distribution", { recursive: true, force: true });
