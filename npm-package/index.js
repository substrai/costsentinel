/**
 * CostSentinel - Real-time GenAI cost governance framework
 *
 * This is the npm placeholder package for CostSentinel.
 * The primary implementation is in Python: pip install substrai-costsentinel
 *
 * TypeScript SDK coming soon.
 *
 * @see https://github.com/substrai/costsentinel
 * @see https://pypi.org/project/substrai-costsentinel/
 */

"use strict";

const VERSION = "0.1.0";

module.exports = {
  VERSION,
  info: () => ({
    name: "substrai-costsentinel",
    version: VERSION,
    description: "Real-time GenAI cost governance framework",
    python_package: "pip install substrai-costsentinel",
    repository: "https://github.com/substrai/costsentinel",
    documentation: "https://docs.substrai.dev/costsentinel",
  }),
};
