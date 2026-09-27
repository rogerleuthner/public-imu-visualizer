// Copyright © 2026 Roger B. Leuthner. All rights reserved.  This software is provided for informational and educational purposes. Use of this software does not imply endorsement by the author of any particular use or application. The author assumes no responsibility or liability for any damages or consequences arising from its use.

import { rename } from "node:fs";
import { cp, mkdir, rm } from "node:fs/promises";
import path from "node:path";

const distribution = "../../distribution";

await rm(distribution, { recursive: true, force: true });

await mkdir(path.join(import.meta.dirname, distribution, "lib"), {
  recursive: true,
});

await cp("dist", path.join(import.meta.dirname, distribution, "www"), {
  recursive: true,
});
await cp(
  "../main/lib/banner.py",
  path.join(import.meta.dirname, distribution, "lib/banner.py"),
  { recursive: false },
);
await cp(
  "../main/lib/lcd1602.py",
  path.join(import.meta.dirname, distribution, "lib/lcd1602.py"),
  { recursive: false },
);
await cp(
  "../main/lib/esp32s_monitor.py",
  path.join(import.meta.dirname, distribution, "lib/esp32s_monitor.py"),
  { recursive: false },
);
await cp(
  "../main/lib/gy521.py",
  path.join(import.meta.dirname, distribution, "lib/gy521.py"),
  { recursive: false },
);
await cp(
  "../main/imu_server.py",
  path.join(import.meta.dirname, distribution, "imu_server.py"),
  { recursive: false },
);
await cp(
  "../main/main.py",
  path.join(import.meta.dirname, distribution, "main.py"),
  { recursive: false },
);
await rename(
  path.join(import.meta.dirname, distribution, "www/version.py"),
  path.join(import.meta.dirname, distribution, "lib/version.py"),
  (err) => {
    if (err) throw err;
  },
);

console.log("Distribution ready:", distribution);
