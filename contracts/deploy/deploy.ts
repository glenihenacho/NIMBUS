import { Wallet, Contract } from "zksync-ethers";
import { HardhatRuntimeEnvironment } from "hardhat/types";
import { Deployer } from "@matterlabs/hardhat-zksync-deploy";
import { ethers } from "ethers";

/**
 * Deployment script for PAT token and DataMarketplace on zkSync Era
 *
 * Usage:
 *   npx hardhat deploy-zksync --script deploy.ts --network zkSyncTestnet
 *   npx hardhat deploy-zksync --script deploy.ts --network zkSyncMainnet
 *
 * For local testing:
 *   npx hardhat test (uses hardhat-upgrades for UUPS proxy)
 */
export default async function (hre: HardhatRuntimeEnvironment) {
  console.log("Deploying PAT ecosystem to zkSync Era...\n");

  // Get wallet from environment
  const wallet = new Wallet(process.env.PRIVATE_KEY!);
  const deployer = new Deployer(hre, wallet);
  const deployerAddress = wallet.address;

  // ============ Deploy PAT Token ============
  console.log("1. Deploying PAT token...");
  const patArtifact = await deployer.loadArtifact("PAT");
  const patToken = await deployer.deploy(patArtifact, []);
  const patAddress = await patToken.getAddress();
  console.log(`   PAT deployed to: ${patAddress}`);

  // ============ Deploy DataMarketplace (UUPS) ============
  console.log("\n2. Deploying DataMarketplace with UUPS proxy...");

  // Configuration
  const brokerWallet = process.env.BROKER_WALLET || deployerAddress;
  const brokerMarginBps = 3000; // 30%

  // Deploy implementation
  const marketplaceArtifact = await deployer.loadArtifact("DataMarketplace");
  const marketplaceImpl = await deployer.deploy(marketplaceArtifact, []);
  const implAddress = await marketplaceImpl.getAddress();
  console.log(`   Implementation: ${implAddress}`);

  // For UUPS on zkSync, deploy via TransparentUpgradeableProxy or ERC1967Proxy
  // Encode initializer (provider earnings held in contract, withdrawn directly)
  const iface = new ethers.Interface(marketplaceArtifact.abi);
  const initData = iface.encodeFunctionData("initialize", [
    patAddress,
    brokerWallet,
    brokerMarginBps
  ]);

  // Deploy proxy from OpenZeppelin
  const proxyArtifact = await deployer.loadArtifact(
    "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol:ERC1967Proxy"
  );
  const proxy = await deployer.deploy(proxyArtifact, [implAddress, initData]);
  const proxyAddress = await proxy.getAddress();
  console.log(`   Proxy: ${proxyAddress}`);

  // Get marketplace instance at proxy address
  const marketplace = new Contract(proxyAddress, marketplaceArtifact.abi, wallet);

  // Verify deployment
  const actualBrokerMargin = await marketplace.brokerMarginBps();
  console.log(`   Verified broker margin: ${actualBrokerMargin / 100}%`);

  // ============ Verify Contracts ============
  console.log("\n3. Verifying contracts...");

  try {
    await hre.run("verify:verify", {
      address: patAddress,
      constructorArguments: [],
    });
    console.log("   PAT verified");
  } catch (e) {
    console.log("   PAT verification skipped");
  }

  try {
    await hre.run("verify:verify", {
      address: implAddress,
      constructorArguments: [],
    });
    console.log("   DataMarketplace verified");
  } catch (e) {
    console.log("   DataMarketplace verification skipped");
  }

  // ============ Summary ============
  console.log("\n" + "=".repeat(50));
  console.log("DEPLOYMENT SUMMARY");
  console.log("=".repeat(50));
  console.log(`Network:            ${hre.network.name}`);
  console.log(`Deployer:           ${deployerAddress}`);
  console.log("");
  console.log(`PAT Token:          ${patAddress}`);
  console.log(`Marketplace Impl:   ${implAddress}`);
  console.log(`Marketplace Proxy:  ${proxyAddress} (interact with this)`);
  console.log("");
  console.log("Configuration:");
  console.log(`  Broker Wallet:    ${brokerWallet}`);
  console.log(`  Broker Margin:    ${brokerMarginBps / 100}%`);
  console.log(`  Note: Provider earnings held in contract, withdrawn directly`);
  console.log("=".repeat(50));

  console.log("\nNEXT STEPS:");
  console.log("1. PAT.distributeAllocation(treasury, ecosystem, ico, team)");
  console.log("2. Approve PAT spending: PAT.approve(proxyAddress, amount)");
  console.log("3. Create segment: marketplace.createSegment(type, days, confidence, price)");
  console.log("4. Buy segment: marketplace.buySegment(segmentId)");
  console.log("5. Withdraw: marketplace.withdrawAllEarnings()");
  console.log("");
  console.log("Upgrade: marketplace.updateBrokerContract(newImpl)");

  return { patToken, marketplace, proxyAddress, implAddress };
}
