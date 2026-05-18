export interface CostSentinelInfo {
  name: string;
  version: string;
  description: string;
  python_package: string;
  repository: string;
  documentation: string;
}

export const VERSION: string;
export function info(): CostSentinelInfo;
