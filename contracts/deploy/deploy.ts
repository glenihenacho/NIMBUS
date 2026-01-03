import { Wallet } from "zksync-ethers";
import { HardhatRuntimeEnvironment } from "hardhat/types";
import { Deployer } from "@matterlabs/hardhat-zksync-deploy";

/**
 * Deployment script for PAT token on zkSync Era
 *
 * Usage:
 *   npx hardhat deploy-zksync --script deploy.ts --network zkSyncTestnet
 *   npx hardhat deploy-zksync --script deploy.ts --network zkSyncMainnet
 */
export default async function (hre: HardhatRuntimeEnvironment) {
  console.log("Deploying PAT token to zkSync Era...");

  // Get wallet from environment
  const wallet = new Wallet(process.env.PRIVATE_KEY!);
  const deployer = new Deployer(hre, wallet);

  // Load the contract artifact
  const artifact = await deployer.loadArtifact("PAT");

  // Deploy the contract
  console.log("Deploying PAT token...");
  const patToken = await deployer.deploy(artifact, []);

  console.log(`PAT token deployed to: ${await patToken.getAddress()}`);
  console.log(`Transaction hash: ${patToken.deploymentTransaction()?.hash}`);

  // Verify contract on block explorer
  console.log("\nVerifying contract...");
  await hre.run("verify:verify", {
    address: await patToken.getAddress(),
    constructorArguments: [],
  });

  console.log("\n=== Deployment Summary ===");
  console.log(`Network: ${hre.network.name}`);
  console.log(`PAT Token: ${await patToken.getAddress()}`);
  console.log(`Total Supply: 555,222,888 PAT`);
  console.log(`\nNext steps:`);
  console.log(`1. Call distributeAllocation() with wallet addresses`);
  console.log(`2. Treasury: 50% (277,611,444 PAT)`);
  console.log(`3. Ecosystem: 30% (166,566,866 PAT)`);
  console.log(`4. ICO: 10% (55,522,289 PAT)`);
  console.log(`5. Team: 10% (55,522,289 PAT) - vested 6-12 months`);

  return patToken;
}
