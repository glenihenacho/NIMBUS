// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Burnable.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title PAT Token
 * @dev ERC-20 token for the PAT ecosystem on zkSync Era
 *
 * Total Supply: 555,222,888 PAT
 * Allocation:
 *   - 50% Treasury (277,611,444 PAT)
 *   - 30% Ecosystem (166,566,866 PAT)
 *   - 10% ICO (55,522,289 PAT)
 *   - 10% Team (55,522,289 PAT) - with 6-12 month linear vesting
 *
 * Jurisdiction: Wyoming DAO LLC
 * Token Type: Utility Token
 */
contract PAT is ERC20, ERC20Burnable, Ownable {
    uint256 public constant TOTAL_SUPPLY = 555_222_888 * 10**18;

    // Allocation percentages (basis points, 10000 = 100%)
    uint256 public constant TREASURY_BPS = 5000;   // 50%
    uint256 public constant ECOSYSTEM_BPS = 3000;  // 30%
    uint256 public constant ICO_BPS = 1000;        // 10%
    uint256 public constant TEAM_BPS = 1000;       // 10%

    // Allocation addresses
    address public treasuryWallet;
    address public ecosystemWallet;
    address public icoWallet;
    address public teamVestingContract;

    // Vesting state for team allocation
    uint256 public teamVestingStart;
    uint256 public teamVestingDuration;
    uint256 public teamTokensReleased;
    uint256 public teamTotalAllocation;

    // Events
    event AllocationDistributed(
        address indexed treasury,
        address indexed ecosystem,
        address indexed ico,
        address team
    );
    event TeamTokensReleased(address indexed to, uint256 amount);

    /**
     * @dev Constructor mints total supply to deployer
     * Call distributeAllocation() after deployment to distribute tokens
     */
    constructor() ERC20("PAT", "PAT") Ownable(msg.sender) {
        _mint(msg.sender, TOTAL_SUPPLY);
    }

    /**
     * @dev Distributes tokens according to allocation percentages
     * @param _treasury Treasury wallet address
     * @param _ecosystem Ecosystem rewards wallet address
     * @param _ico ICO distribution wallet address
     * @param _teamVesting Team vesting contract address
     * @param _vestingDuration Duration of team vesting in seconds (6-12 months)
     */
    function distributeAllocation(
        address _treasury,
        address _ecosystem,
        address _ico,
        address _teamVesting,
        uint256 _vestingDuration
    ) external onlyOwner {
        require(treasuryWallet == address(0), "Already distributed");
        require(_treasury != address(0), "Invalid treasury");
        require(_ecosystem != address(0), "Invalid ecosystem");
        require(_ico != address(0), "Invalid ico");
        require(_teamVesting != address(0), "Invalid team vesting");
        require(_vestingDuration >= 180 days, "Vesting too short");
        require(_vestingDuration <= 365 days, "Vesting too long");

        treasuryWallet = _treasury;
        ecosystemWallet = _ecosystem;
        icoWallet = _ico;
        teamVestingContract = _teamVesting;

        uint256 treasuryAmount = (TOTAL_SUPPLY * TREASURY_BPS) / 10000;
        uint256 ecosystemAmount = (TOTAL_SUPPLY * ECOSYSTEM_BPS) / 10000;
        uint256 icoAmount = (TOTAL_SUPPLY * ICO_BPS) / 10000;
        uint256 teamAmount = TOTAL_SUPPLY - treasuryAmount - ecosystemAmount - icoAmount;

        // Transfer allocations
        _transfer(owner(), _treasury, treasuryAmount);
        _transfer(owner(), _ecosystem, ecosystemAmount);
        _transfer(owner(), _ico, icoAmount);

        // Team tokens stay with contract for vesting
        teamTotalAllocation = teamAmount;
        teamVestingStart = block.timestamp;
        teamVestingDuration = _vestingDuration;

        emit AllocationDistributed(_treasury, _ecosystem, _ico, _teamVesting);
    }

    /**
     * @dev Returns the amount of team tokens that can be released
     */
    function releasableTeamTokens() public view returns (uint256) {
        if (teamVestingStart == 0) return 0;

        uint256 elapsed = block.timestamp - teamVestingStart;
        if (elapsed >= teamVestingDuration) {
            return teamTotalAllocation - teamTokensReleased;
        }

        uint256 vested = (teamTotalAllocation * elapsed) / teamVestingDuration;
        return vested - teamTokensReleased;
    }

    /**
     * @dev Releases vested team tokens to the team vesting contract
     */
    function releaseTeamTokens() external {
        require(teamVestingContract != address(0), "Not initialized");

        uint256 releasable = releasableTeamTokens();
        require(releasable > 0, "No tokens to release");

        teamTokensReleased += releasable;
        _transfer(owner(), teamVestingContract, releasable);

        emit TeamTokensReleased(teamVestingContract, releasable);
    }

    /**
     * @dev Returns token allocation amounts
     */
    function getAllocationAmounts() external pure returns (
        uint256 treasury,
        uint256 ecosystem,
        uint256 ico,
        uint256 team
    ) {
        treasury = (TOTAL_SUPPLY * TREASURY_BPS) / 10000;
        ecosystem = (TOTAL_SUPPLY * ECOSYSTEM_BPS) / 10000;
        ico = (TOTAL_SUPPLY * ICO_BPS) / 10000;
        team = TOTAL_SUPPLY - treasury - ecosystem - ico;
    }
}
