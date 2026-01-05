import { expect } from "chai";
import { ethers } from "hardhat";
import { PAT, DataMarketplace } from "../typechain-types";
import { SignerWithAddress } from "@nomicfoundation/hardhat-ethers/signers";

describe("DataMarketplace", function () {
  let pat: PAT;
  let marketplace: DataMarketplace;
  let owner: SignerWithAddress;
  let broker: SignerWithAddress;
  let provider: SignerWithAddress;
  let consumer: SignerWithAddress;
  let usersPool: SignerWithAddress;

  const BROKER_MARGIN_BPS = 3000; // 30%
  const SEGMENT_PRICE = ethers.parseEther("100"); // 100 PAT

  beforeEach(async function () {
    [owner, broker, provider, consumer, usersPool] = await ethers.getSigners();

    // Deploy PAT token
    const PATFactory = await ethers.getContractFactory("PAT");
    pat = await PATFactory.deploy();
    await pat.waitForDeployment();

    // Deploy DataMarketplace
    const MarketplaceFactory = await ethers.getContractFactory("DataMarketplace");
    marketplace = await MarketplaceFactory.deploy(
      await pat.getAddress(),
      broker.address,
      usersPool.address,
      BROKER_MARGIN_BPS
    );
    await marketplace.waitForDeployment();

    // Transfer some PAT to consumer for testing
    await pat.transfer(consumer.address, ethers.parseEther("1000"));
  });

  describe("Deployment", function () {
    it("Should set correct initial configuration", async function () {
      expect(await marketplace.brokerWallet()).to.equal(broker.address);
      expect(await marketplace.usersPoolWallet()).to.equal(usersPool.address);
      expect(await marketplace.brokerMarginBps()).to.equal(BROKER_MARGIN_BPS);
      expect(await marketplace.getPhaseString()).to.equal("UTILITY");
      expect(await marketplace.paused()).to.equal(false);
    });

    it("Should reject invalid broker margin", async function () {
      const MarketplaceFactory = await ethers.getContractFactory("DataMarketplace");
      await expect(
        MarketplaceFactory.deploy(
          await pat.getAddress(),
          broker.address,
          usersPool.address,
          6000 // > 50%
        )
      ).to.be.revertedWith("Margin too high");
    });
  });

  describe("Segment Creation", function () {
    it("Should create a segment", async function () {
      const tx = await marketplace.connect(provider).createSegment(
        0, // PURCHASE_INTENT
        7, // 7 days
        7500, // 75% confidence
        SEGMENT_PRICE
      );

      await expect(tx)
        .to.emit(marketplace, "SegmentCreated")
        .withArgs(0, provider.address, 0, SEGMENT_PRICE);

      const segment = await marketplace.getSegment(0);
      expect(segment.segmentType).to.equal(0);
      expect(segment.windowDays).to.equal(7);
      expect(segment.confidenceBps).to.equal(7500);
      expect(segment.askPrice).to.equal(SEGMENT_PRICE);
      expect(segment.provider).to.equal(provider.address);
      expect(segment.active).to.equal(true);
    });

    it("Should reject invalid window", async function () {
      await expect(
        marketplace.connect(provider).createSegment(0, 0, 7500, SEGMENT_PRICE)
      ).to.be.revertedWith("Invalid window");

      await expect(
        marketplace.connect(provider).createSegment(0, 31, 7500, SEGMENT_PRICE)
      ).to.be.revertedWith("Invalid window");
    });
  });

  describe("Atomic Settlement", function () {
    beforeEach(async function () {
      // Create a segment
      await marketplace.connect(provider).createSegment(
        0, // PURCHASE_INTENT
        7,
        7500,
        SEGMENT_PRICE
      );

      // Consumer approves marketplace
      await pat.connect(consumer).approve(
        await marketplace.getAddress(),
        SEGMENT_PRICE
      );
    });

    it("Should atomically settle purchase", async function () {
      const providerBalanceBefore = await pat.balanceOf(provider.address);
      const brokerBalanceBefore = await pat.balanceOf(broker.address);
      const consumerBalanceBefore = await pat.balanceOf(consumer.address);

      // Calculate expected split
      const expectedBrokerSpread = (SEGMENT_PRICE * BigInt(BROKER_MARGIN_BPS)) / 10000n;
      const expectedProviderPayout = SEGMENT_PRICE - expectedBrokerSpread;

      // Buy segment
      const tx = await marketplace.connect(consumer).buySegment(0);

      await expect(tx)
        .to.emit(marketplace, "SegmentPurchased")
        .withArgs(
          0,
          consumer.address,
          provider.address,
          SEGMENT_PRICE,
          expectedProviderPayout,
          expectedBrokerSpread
        );

      // Verify balances
      expect(await pat.balanceOf(provider.address)).to.equal(
        providerBalanceBefore + expectedProviderPayout
      );
      expect(await pat.balanceOf(broker.address)).to.equal(
        brokerBalanceBefore + expectedBrokerSpread
      );
      expect(await pat.balanceOf(consumer.address)).to.equal(
        consumerBalanceBefore - SEGMENT_PRICE
      );

      // Verify access granted
      expect(await marketplace.hasAccess(consumer.address, 0)).to.equal(true);
    });

    it("Should calculate split correctly", async function () {
      const [providerPayout, brokerSpread] = await marketplace.calculateSplit(SEGMENT_PRICE);

      expect(brokerSpread).to.equal((SEGMENT_PRICE * BigInt(BROKER_MARGIN_BPS)) / 10000n);
      expect(providerPayout).to.equal(SEGMENT_PRICE - brokerSpread);
      expect(providerPayout + brokerSpread).to.equal(SEGMENT_PRICE);
    });

    it("Should reject purchase without approval", async function () {
      // Create new segment
      await marketplace.connect(provider).createSegment(0, 7, 7500, SEGMENT_PRICE);

      // Try to buy without approval
      await expect(
        marketplace.connect(consumer).buySegment(1)
      ).to.be.revertedWithCustomError(marketplace, "InsufficientAllowance");
    });

    it("Should reject duplicate purchase", async function () {
      await marketplace.connect(consumer).buySegment(0);

      // Approve again
      await pat.connect(consumer).approve(
        await marketplace.getAddress(),
        SEGMENT_PRICE
      );

      await expect(
        marketplace.connect(consumer).buySegment(0)
      ).to.be.revertedWithCustomError(marketplace, "AlreadyHasAccess");
    });

    it("Should reject purchase of inactive segment", async function () {
      await marketplace.connect(provider).deactivateSegment(0);

      await expect(
        marketplace.connect(consumer).buySegment(0)
      ).to.be.revertedWithCustomError(marketplace, "SegmentNotActive");
    });
  });

  describe("Governance - updateBrokerContract()", function () {
    it("Should update broker margin via unified function", async function () {
      const encoded = ethers.AbiCoder.defaultAbiCoder().encode(["uint256"], [2000]);
      await marketplace.updateBrokerContract("brokerMargin", encoded);
      expect(await marketplace.brokerMarginBps()).to.equal(2000);
    });

    it("Should reject margin > 50%", async function () {
      const encoded = ethers.AbiCoder.defaultAbiCoder().encode(["uint256"], [5001]);
      await expect(
        marketplace.updateBrokerContract("brokerMargin", encoded)
      ).to.be.revertedWithCustomError(marketplace, "InvalidConfiguration");
    });

    it("Should update broker wallet via unified function", async function () {
      const newBroker = consumer.address;
      const encoded = ethers.AbiCoder.defaultAbiCoder().encode(["address"], [newBroker]);
      await marketplace.updateBrokerContract("brokerWallet", encoded);
      expect(await marketplace.brokerWallet()).to.equal(newBroker);
    });

    it("Should update users pool wallet via unified function", async function () {
      const newPool = consumer.address;
      const encoded = ethers.AbiCoder.defaultAbiCoder().encode(["address"], [newPool]);
      await marketplace.updateBrokerContract("usersPoolWallet", encoded);
      expect(await marketplace.usersPoolWallet()).to.equal(newPool);
    });

    it("Should advance phase via unified function", async function () {
      expect(await marketplace.getPhaseString()).to.equal("UTILITY");

      // Advance to FORWARDS (phase 1)
      let encoded = ethers.AbiCoder.defaultAbiCoder().encode(["uint8"], [1]);
      await marketplace.updateBrokerContract("phase", encoded);
      expect(await marketplace.getPhaseString()).to.equal("FORWARDS");

      // Advance to SYNTHETICS (phase 2)
      encoded = ethers.AbiCoder.defaultAbiCoder().encode(["uint8"], [2]);
      await marketplace.updateBrokerContract("phase", encoded);
      expect(await marketplace.getPhaseString()).to.equal("SYNTHETICS");

      // Advance to SPECULATION (phase 3)
      encoded = ethers.AbiCoder.defaultAbiCoder().encode(["uint8"], [3]);
      await marketplace.updateBrokerContract("phase", encoded);
      expect(await marketplace.getPhaseString()).to.equal("SPECULATION");

      // Cannot go past final phase
      encoded = ethers.AbiCoder.defaultAbiCoder().encode(["uint8"], [4]);
      await expect(
        marketplace.updateBrokerContract("phase", encoded)
      ).to.be.revertedWith("Invalid phase");
    });

    it("Should reject phase regression", async function () {
      // Advance to phase 2
      let encoded = ethers.AbiCoder.defaultAbiCoder().encode(["uint8"], [2]);
      await marketplace.updateBrokerContract("phase", encoded);

      // Try to go back to phase 1
      encoded = ethers.AbiCoder.defaultAbiCoder().encode(["uint8"], [1]);
      await expect(
        marketplace.updateBrokerContract("phase", encoded)
      ).to.be.revertedWith("Can only advance phase");
    });

    it("Should pause and unpause via unified function", async function () {
      let encoded = ethers.AbiCoder.defaultAbiCoder().encode(["bool"], [true]);
      await marketplace.updateBrokerContract("paused", encoded);
      expect(await marketplace.paused()).to.equal(true);

      await expect(
        marketplace.connect(provider).createSegment(0, 7, 7500, SEGMENT_PRICE)
      ).to.be.revertedWithCustomError(marketplace, "MarketPaused");

      encoded = ethers.AbiCoder.defaultAbiCoder().encode(["bool"], [false]);
      await marketplace.updateBrokerContract("paused", encoded);
      await marketplace.connect(provider).createSegment(0, 7, 7500, SEGMENT_PRICE);
    });

    it("Should reject invalid paramKey", async function () {
      const encoded = ethers.AbiCoder.defaultAbiCoder().encode(["uint256"], [100]);
      await expect(
        marketplace.updateBrokerContract("invalidKey", encoded)
      ).to.be.revertedWithCustomError(marketplace, "InvalidConfiguration");
    });

    it("Should reject non-owner governance calls", async function () {
      const encoded = ethers.AbiCoder.defaultAbiCoder().encode(["uint256"], [2000]);
      await expect(
        marketplace.connect(consumer).updateBrokerContract("brokerMargin", encoded)
      ).to.be.revertedWithCustomError(marketplace, "OwnableUnauthorizedAccount");
    });
  });

  describe("Provider Functions", function () {
    beforeEach(async function () {
      await marketplace.connect(provider).createSegment(0, 7, 7500, SEGMENT_PRICE);
    });

    it("Should update segment price", async function () {
      const newPrice = ethers.parseEther("150");
      await marketplace.connect(provider).updateSegmentPrice(0, newPrice);

      const segment = await marketplace.getSegment(0);
      expect(segment.askPrice).to.equal(newPrice);
    });

    it("Should deactivate segment", async function () {
      await marketplace.connect(provider).deactivateSegment(0);

      const segment = await marketplace.getSegment(0);
      expect(segment.active).to.equal(false);
    });

    it("Should reject non-provider updates", async function () {
      await expect(
        marketplace.connect(consumer).updateSegmentPrice(0, SEGMENT_PRICE)
      ).to.be.revertedWith("Not provider");

      await expect(
        marketplace.connect(consumer).deactivateSegment(0)
      ).to.be.revertedWith("Not provider");
    });
  });
});
